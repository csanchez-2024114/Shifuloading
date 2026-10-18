"""Archivos en el store de LangGraph del agente (el mismo de la memoria: MongoDBStore o InMemoryStore), separados por
usuario y por hilo. Se guarda lo extraído (texto por página y la imagen ya reducida), no el archivo original. Todo se
escribe con index=False: nada de esto se embebe ni aparece en la búsqueda de recuerdos."""
import time
import uuid

LIMIT = 1000


def _meta_ns(user_id: str, thread_id: str) -> tuple:
    return ("files", user_id, thread_id)


def _pages_ns(user_id: str, thread_id: str, file_id: str) -> tuple:
    return ("file_pages", user_id, thread_id, file_id)


def _image_ns(user_id: str, thread_id: str) -> tuple:
    return ("file_images", user_id, thread_id)


def save(store, user_id: str, thread_id: str, name: str, kind: str, mime: str, size: int, sha256: str,
         extracted: dict) -> dict:
    file_id = uuid.uuid4().hex[:16]
    meta = {"file_id": file_id, "name": name, "kind": kind, "mime": mime, "size": size, "sha256": sha256,
            "pages": len(extracted["pages"]), "chars": extracted["chars"], "truncated": extracted["truncated"],
            "created_at": time.time()}
    for n, text in enumerate(extracted["pages"], 1):
        store.put(_pages_ns(user_id, thread_id, file_id), f"{n:04d}", {"n": n, "text": text}, index=False)
    if extracted.get("image"):
        store.put(_image_ns(user_id, thread_id), file_id, extracted["image"], index=False)
    store.put(_meta_ns(user_id, thread_id), file_id, meta, index=False)  # al final: un archivo a medias no se lista
    return meta


def list_files(store, user_id: str, thread_id: str) -> list[dict]:
    items = store.search(_meta_ns(user_id, thread_id), limit=LIMIT)
    return sorted((i.value for i in items), key=lambda m: m.get("created_at", 0))


def get(store, user_id: str, thread_id: str, file_id: str) -> dict | None:
    item = store.get(_meta_ns(user_id, thread_id), file_id)
    return item.value if item else None


def pages(store, user_id: str, thread_id: str, file_id: str) -> list[str]:
    items = store.search(_pages_ns(user_id, thread_id, file_id), limit=LIMIT)
    return [i.value["text"] for i in sorted(items, key=lambda i: i.key)]


def image(store, user_id: str, thread_id: str, file_id: str) -> dict | None:
    item = store.get(_image_ns(user_id, thread_id), file_id)
    return item.value if item else None


def delete(store, user_id: str, thread_id: str, file_id: str) -> bool:
    if get(store, user_id, thread_id, file_id) is None:
        return False
    store.delete(_meta_ns(user_id, thread_id), file_id)
    for item in store.search(_pages_ns(user_id, thread_id, file_id), limit=LIMIT):
        store.delete(item.namespace, item.key)
    store.delete(_image_ns(user_id, thread_id), file_id)
    return True


def delete_thread(store, user_id: str, thread_id: str) -> int:
    files = list_files(store, user_id, thread_id)
    for meta in files:
        delete(store, user_id, thread_id, meta["file_id"])
    return len(files)


def delete_user(store, user_id: str) -> int:
    """Todos los archivos del usuario, en todos sus hilos (borrar la cuenta)."""
    count = 0
    for prefix in (("files", user_id), ("file_pages", user_id), ("file_images", user_id)):
        while items := store.search(prefix, limit=LIMIT):
            for item in items:
                store.delete(item.namespace, item.key)
                count += prefix[0] == "files"
    return count
