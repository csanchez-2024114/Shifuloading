"""
backfill_message_index.py — indexa en user_message_index los mensajes del usuario (chat_messages, role "user") escritos
antes de que memory_updater los guardara, para que search_older_messages los encuentre por significado.

    python scripts/backfill_message_index.py --dry-run   # solo cuenta y estima el costo (no llama a OpenAI)
    python scripts/backfill_message_index.py             # calcula y guarda; usa OpenAI real

Usa MONGO_URI / MONGO_DB_NAME del .env. Idempotente: salta lo ya indexado (mismo usuario + conversacion + texto),
lo trivial y todo texto que parezca credencial (las mismas reglas que el indexado en vivo).
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")  # antes de importar app.*: OpenAIEmbeddings se crea a nivel de modulo
sys.stdout.reconfigure(encoding="utf-8")
from pymongo import MongoClient  # noqa: E402

from app.agent.shared.memory.message_index import INDEX, MAX_CHARS, indexable  # noqa: E402

PRICE_PER_M_TOKENS = 0.02  # text-embedding-3-small, USD por millon de tokens
CHARS_PER_TOKEN = 4  # estimacion gruesa


def pending_messages(db) -> tuple[list[dict], int]:
    """Mensajes del usuario aun sin indexar y cuantos se descartaron (trivial/credencial/ya indexado)."""
    done = {(d["user_id"], d["conversation_id"], d["text"]) for d in db[INDEX].find({}, {"user_id": 1, "conversation_id": 1, "text": 1})}
    todo, skipped = [], 0
    for m in db.chat_messages.find({"role": "user"}, {"user_id": 1, "conversation_id": 1, "content": 1, "created_at": 1}):
        text = m.get("content")
        text = text.strip()[:MAX_CHARS] if isinstance(text, str) else ""
        key = (m.get("user_id"), m.get("conversation_id") or "", text)
        if not m.get("user_id") or not indexable(text) or key in done:
            skipped += 1
            continue
        done.add(key)  # el mismo texto repetido en la misma conversacion se indexa una vez
        todo.append({"user_id": key[0], "conversation_id": key[1], "text": text, "created_at": m.get("created_at")})
    return todo, skipped


async def main(dry_run: bool) -> None:
    db = MongoClient(os.environ["MONGO_URI"])[os.environ.get("MONGO_DB_NAME", "shifu")]
    todo, skipped = pending_messages(db)
    chars = sum(len(m["text"]) for m in todo)
    cost = chars / CHARS_PER_TOKEN / 1_000_000 * PRICE_PER_M_TOKENS
    print(f"Mensajes por indexar: {len(todo)}  (omitidos: {skipped}; ~{chars // CHARS_PER_TOKEN} tokens, costo estimado ~${cost:.5f} USD)")
    if dry_run or not todo:
        return

    from app.agent.shared.memory.memory_embedder import embed_text

    done = failed = 0
    for m in todo:
        emb = await embed_text(m["text"])
        if not emb:
            failed += 1  # se reintenta en la siguiente corrida
            continue
        when = m["created_at"] if isinstance(m["created_at"], datetime) else datetime.now(timezone.utc)
        db[INDEX].insert_one({**m, "date": when.strftime("%Y-%m-%d"), "embedding": emb, "created_at": when})
        done += 1
    print(f"Listo: {done} indexados, {failed} fallaron")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
