"""Indexa para la búsqueda semántica (Atlas, MEMORY_SEMANTIC=1) los recuerdos guardados sin embedding.

Los recuerdos guardados antes de activar MEMORY_SEMANTIC no tienen vector y no aparecen en la búsqueda semántica.
Este script les agrega SOLO lo que el índice necesita (`embedding` y `namespace_prefix`, igual que MongoDBStore al
guardar). No cambia ningún otro campo: ni `value` (text, created_at, evidence, confidence, previous_text...) ni las
fechas del documento. Es idempotente: solo toca documentos sin `embedding`, así que repetirlo no cambia nada.

Uso (lee MONGODB_URI, MONGODB_DB, OPENAI_API_KEY y EMBEDDING_MODEL de .env):
    python scripts/migrate_memories.py            # dry-run (por defecto): solo informa, no escribe
    python scripts/migrate_memories.py --apply    # escribe
    python scripts/migrate_memories.py --db otra_base
"""
import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

SEP = "/"  # separador de namespace de MongoDBStore (default)
PENDING = {"namespace.0": "user", "namespace.2": "memories", "value.text": {"$type": "string"},
           "embedding": {"$exists": False}}


def namespace_prefix(namespace: list[str]) -> list[str]:
    """Igual que MongoDBStore._denormalize_path: ['user', 'user/u1', 'user/u1/memories']."""
    return [SEP.join(namespace[:i]) for i in range(1, len(namespace) + 1)]


def migrate(collection, embed_documents: Callable[[list[str]], list[list[float]]], *, apply: bool = False,
            count_tokens: Callable[[str], int] = lambda t: len(t) // 4, batch: int = 64) -> dict:
    docs = list(collection.find(PENDING, {"_id": 1, "namespace": 1, "value.text": 1}))
    users = Counter(d["namespace"][1] for d in docs)
    report = {"pending": len(docs), "users": len(users), "per_user": dict(users),
              "estimated_tokens": sum(count_tokens(d["value"]["text"]) for d in docs), "updated": 0, "applied": apply}
    if not apply:
        return report
    for i in range(0, len(docs), batch):
        chunk = docs[i:i + batch]
        vectors = embed_documents([d["value"]["text"] for d in chunk])
        for doc, vector in zip(chunk, vectors):
            # la condición repite "sin embedding": si otro proceso ya lo indexó, no se toca
            result = collection.update_one({"_id": doc["_id"], "embedding": {"$exists": False}},
                                           {"$set": {"embedding": vector, "namespace_prefix": namespace_prefix(doc["namespace"])}})
            report["updated"] += result.modified_count
    return report


def main(argv=None) -> int:
    from assistant import memory
    from assistant.config import ConfigError, Settings

    parser = argparse.ArgumentParser(description="Indexa recuerdos sin embedding (dry-run por defecto).")
    parser.add_argument("--apply", action="store_true", help="escribe en la base (sin esto solo informa)")
    parser.add_argument("--db", help="base de datos (default: MONGODB_DB de .env)")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    db = args.db or settings.mongodb_db
    try:
        client = memory.ping_mongo(settings.mongodb_uri)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    embed = None
    if args.apply:
        settings.require_api_key()
        from langchain_openai import OpenAIEmbeddings

        embed = OpenAIEmbeddings(model=memory.EMBEDDING_MODEL, api_key=settings.openai_api_key).embed_documents
    host = settings.mongodb_uri.rsplit("@", 1)[-1]
    report = migrate(client[db][memory.STORE_COLLECTION], embed, apply=args.apply,
                     count_tokens=lambda t: len(enc.encode(t)))
    print(f"{'APPLY' if args.apply else 'DRY-RUN (no se escribió nada)'} | {host} | base {db}")
    print(f"Recuerdos sin embedding: {report['pending']} de {report['users']} usuario(s)")
    for user, n in sorted(report["per_user"].items()):
        print(f"  - {user}: {n}")
    print(f"Costo estimado: ~{report['estimated_tokens']} tokens de embeddings ({memory.EMBEDDING_MODEL})")
    if args.apply:
        print(f"Indexados: {report['updated']}")
    else:
        print("Para escribir: python scripts/migrate_memories.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
