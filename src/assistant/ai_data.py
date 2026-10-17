"""Borrado en la base de la IA: checkpoints de un hilo (mensajes, resúmenes, métricas de contexto, herramientas
elegidas por bigtool) y la memoria global de un usuario. Solo conoce user_id opacos y thread_id."""
from assistant import memory

_BATCH = 100


def delete_thread(checkpointer, thread_id: str) -> None:
    checkpointer.delete_thread(thread_id)


def delete_user_memories(store, user_id: str) -> int:
    """Borra todos los recuerdos del namespace del usuario. Devuelve cuántos."""
    if store is None:
        return 0
    deleted = 0
    while items := store.search(memory.memory_namespace(user_id), limit=_BATCH):
        for item in items:
            store.delete(memory.memory_namespace(user_id), item.key)
            deleted += 1
    return deleted


def delete_user_ai_data(checkpointer, store, user_id: str, thread_ids) -> dict:
    """Todos los datos de un usuario en la base de la IA: sus hilos y su memoria global."""
    thread_ids = list(thread_ids)
    for tid in thread_ids:
        delete_thread(checkpointer, tid)
    return {"threads": len(thread_ids), "memories": delete_user_memories(store, user_id)}
