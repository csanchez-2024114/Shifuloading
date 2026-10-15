"""scripts/migrate_memories.py: agrega solo embedding + namespace_prefix, conserva todo lo demás y es idempotente."""
import importlib.util
from pathlib import Path

from langchain_core.embeddings.fake import DeterministicFakeEmbedding

from conftest import TEST_DB, uid

_spec = importlib.util.spec_from_file_location(
    "migrate_memories", Path(__file__).resolve().parents[1] / "scripts" / "migrate_memories.py")
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


def test_migracion_conserva_campos_y_es_idempotente(mongo_client, store):
    from assistant import memory

    col = mongo_client[TEST_DB][memory.STORE_COLLECTION]
    a, b = uid("a"), uid("b")
    store.put(memory.memory_namespace(a), "viejo", {"text": "Le gusta el jazz"})  # recuerdo antiguo, solo text
    k1 = memory.save_memory(store, a, "Vive en Puebla", thread_id="t1", evidence="vivo en Puebla", confidence="quoted")
    k2 = memory.save_memory(store, b, "Su bebida es el café")
    memory.update_memory(store, b, k2, "Su bebida es el té verde", evidence="ahora té verde", confidence="verified")
    store.put(("otra", "cosa"), "x", {"text": "no es un recuerdo"})  # otro namespace: no se toca
    k4 = memory.save_memory(store, a, "Ya indexado")
    col.update_one({"key": k4}, {"$set": {"embedding": [0.5] * 8, "namespace_prefix": ["user"]}})  # ya tenía vector
    keys = ["viejo", k1, k2]

    def snapshot():
        return {d["key"]: d for d in col.find({"key": {"$in": keys + ["x", k4]}})}

    antes = snapshot()
    embed = DeterministicFakeEmbedding(size=8).embed_documents

    dry = mig.migrate(col, embed)  # dry-run por defecto
    assert dry["pending"] >= 3 and dry["updated"] == 0 and not dry["applied"]
    assert {a, b} <= set(dry["per_user"]) and dry["estimated_tokens"] > 0
    assert snapshot() == antes  # no escribió nada

    res = mig.migrate(col, embed, apply=True)
    assert res["updated"] == res["pending"] >= 3
    despues = snapshot()
    for k in keys:
        nuevos = set(despues[k]) - set(antes[k])
        assert nuevos == {"embedding", "namespace_prefix"}
        assert {f: despues[k][f] for f in antes[k]} == antes[k]  # ningún valor existente cambió
        assert despues[k]["namespace_prefix"] == mig.namespace_prefix(despues[k]["namespace"])
    assert despues["x"] == antes["x"] and despues[k4] == antes[k4]  # ya indexado: intacto
    assert despues[k2]["value"]["previous_text"] == "Su bebida es el café"  # campos de procedencia intactos

    otra = mig.migrate(col, embed, apply=True)  # segunda ejecución: nada pendiente, nada cambia
    assert otra["pending"] == 0 and otra["updated"] == 0
    assert snapshot() == despues
