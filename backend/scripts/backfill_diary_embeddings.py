"""
backfill_diary_embeddings.py — calcula el embedding de las entradas de user_daily_diary que no lo tienen
(las escritas antes de que memory_learner lo guardara), para que search_older las encuentre por significado.

    python scripts/backfill_diary_embeddings.py --dry-run   # solo cuenta y estima el costo (no llama a OpenAI)
    python scripts/backfill_diary_embeddings.py             # calcula y guarda ($set embedding); usa OpenAI real

Usa MONGO_URI / MONGO_DB_NAME del .env. Es idempotente: solo toca las entradas sin embedding.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")  # antes de importar app.*: OpenAIEmbeddings se crea a nivel de modulo
sys.stdout.reconfigure(encoding="utf-8")
from pymongo import MongoClient  # noqa: E402

PRICE_PER_M_TOKENS = 0.02  # text-embedding-3-small, USD por millon de tokens
CHARS_PER_TOKEN = 4  # estimacion gruesa


def diary_text(doc: dict) -> str:
    # Mismo texto que memory_learner.learn: resumen + pendiente.
    summary = (doc.get("activities") or [""])[0]
    return f"{summary} {doc.get('pending') or ''}".strip()


async def main(dry_run: bool) -> None:
    db = MongoClient(os.environ["MONGO_URI"])[os.environ.get("MONGO_DB_NAME", "shifu")]
    docs = list(db.user_daily_diary.find({"embedding": {"$exists": False}}, {"activities": 1, "pending": 1}))
    texts = {d["_id"]: diary_text(d) for d in docs}
    chars = sum(min(len(t), 2000) for t in texts.values())
    cost = chars / CHARS_PER_TOKEN / 1_000_000 * PRICE_PER_M_TOKENS
    print(f"Entradas sin embedding: {len(docs)}  (~{chars // CHARS_PER_TOKEN} tokens, costo estimado ~${cost:.5f} USD)")
    if dry_run or not docs:
        return

    from app.agent.shared.memory.memory_embedder import embed_text

    done = skipped = 0
    for _id, text in texts.items():
        emb = await embed_text(text) if text else None
        if emb:
            db.user_daily_diary.update_one({"_id": _id}, {"$set": {"embedding": emb}})
            done += 1
        else:
            skipped += 1  # sin texto o fallo del embedding; se reintenta en la siguiente corrida
    print(f"Listo: {done} con embedding, {skipped} omitidas")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
