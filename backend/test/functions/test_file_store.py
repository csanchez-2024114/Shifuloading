import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import file_storage, file_store

PDF = b"%PDF-1.4 hola"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIFU_UPLOAD_DIR", str(tmp_path))
    monkeypatch.delenv("FILE_STORAGE", raising=False)
    return AsyncMongoMockClient()["files_test"]


class Memory:
    """Un servicio de mentira: lo mismo que pide file_storage a cualquiera (put, get, delete)."""

    def __init__(self):
        self.blobs = {}

    async def put(self, key, data):
        self.blobs[key] = data

    async def get(self, key):
        return self.blobs[key]

    async def delete(self, key):
        self.blobs.pop(key, None)


async def test_local_guarda_en_disco_y_borra(db, tmp_path):
    meta = await file_store.save(db, "u1", "../../fuera.pdf", PDF)
    on_disk = list(tmp_path.rglob("*.pdf"))
    assert [p.read_bytes() for p in on_disk] == [PDF] and on_disk[0].parent == tmp_path / "u1"  # el nombre del usuario no decide la ruta
    await file_store.delete(db, "u1", meta["file_id"])
    assert list(tmp_path.rglob("*.pdf")) == []


async def test_cambiar_de_servicio_no_pierde_los_archivos_viejos(db, monkeypatch):
    other = Memory()
    monkeypatch.setitem(file_storage.BACKENDS, "otro", other)
    old = await file_store.save(db, "u1", "viejo.pdf", PDF)
    monkeypatch.setenv("FILE_STORAGE", "otro")
    new = await file_store.save(db, "u1", "nuevo.pdf", PDF + b"2")
    assert list(other.blobs.values()) == [PDF + b"2"]
    assert (await file_store.read(db, "u1", old["file_id"]))[1] == PDF        # sigue en disco
    assert (await file_store.read(db, "u1", new["file_id"]))[1] == PDF + b"2"  # este ya en el servicio nuevo
    await file_store.delete(db, "u1", new["file_id"])
    assert other.blobs == {}


async def test_servicio_desconocido_falla_al_subir(db, monkeypatch):
    monkeypatch.setenv("FILE_STORAGE", "s4")
    with pytest.raises(RuntimeError):
        await file_store.save(db, "u1", "a.pdf", PDF)


async def test_cloudinary_sube_y_borra_privado_y_crudo(monkeypatch):
    calls = []
    uploader = type("U", (), {"upload": lambda f, **kw: calls.append(("upload", f.read(), kw)),
                              "destroy": lambda pid, **kw: calls.append(("destroy", pid, kw))})
    monkeypatch.setattr(file_storage.Cloudinary, "_sdk", staticmethod(lambda: type("S", (), {"uploader": uploader})))
    cloud = file_storage.Cloudinary()
    await cloud.put("u1/abc.pdf", PDF)
    await cloud.delete("u1/abc.pdf")
    assert calls[0] == ("upload", PDF, {"public_id": "shifu_files/u1/abc.pdf", "overwrite": False, "resource_type": "raw", "type": "authenticated"})
    assert calls[1] == ("destroy", "shifu_files/u1/abc.pdf", {"invalidate": True, "resource_type": "raw", "type": "authenticated"})


async def test_sube_lee_lista_y_borra(db):
    meta = await file_store.save(db, "u1", "C:\\docs\\Factura.PDF", PDF, "application/pdf")
    assert meta["name"] == "Factura.PDF" and meta["kind"] == "document" and meta["size"] == len(PDF)
    assert (await file_store.read(db, "u1", meta["file_id"]))[1] == PDF
    assert [f["file_id"] for f in await file_store.list_files(db, "u1")] == [meta["file_id"]]
    assert await file_store.delete(db, "u1", meta["file_id"])
    assert await file_store.read(db, "u1", meta["file_id"]) is None


async def test_otro_usuario_no_lo_ve_ni_lo_adjunta_ni_lo_borra(db):
    meta = await file_store.save(db, "u1", "a.pdf", PDF)
    assert await file_store.read(db, "u2", meta["file_id"]) is None
    assert await file_store.resources(db, "u2", [meta["file_id"]]) == []
    assert not await file_store.delete(db, "u2", meta["file_id"])
    assert await file_store.list_files(db, "u2") == []


async def test_resources_arma_el_adjunto_y_descarta_ids_malos(db):
    meta = await file_store.save(db, "u1", "foto.png", b"\x89PNG....")
    got = await file_store.resources(db, "u1", [meta["file_id"], "no-es-un-id", "https://interno/secreto", None])
    assert got == [{"type": "image", "url": file_store.SCHEME + meta["file_id"], "title": "foto.png",
                    "provider": "upload", "file_id": meta["file_id"], "metadata": {"size": 8}}]
    assert await file_store.resources(db, "u1", "no-es-lista") == []


@pytest.mark.parametrize("name,data", [
    ("virus.exe", b"MZ"),                 # tipo no admitido
    ("falso.pdf", b"MZ esto es un exe"),  # la extension miente
    ("vacio.txt", b""),
])
async def test_rechaza(db, name, data):
    with pytest.raises(file_store.FileRejected):
        await file_store.save(db, "u1", name, data)


async def test_rechaza_por_tamano_y_por_tope(db, monkeypatch):
    monkeypatch.setattr(file_store, "MAX_BYTES", 10)
    with pytest.raises(file_store.FileRejected):
        await file_store.save(db, "u1", "grande.txt", b"x" * 11)
    monkeypatch.setattr(file_store, "MAX_FILES_PER_USER", 1)
    await file_store.save(db, "u1", "uno.txt", b"1")
    with pytest.raises(file_store.FileRejected):
        await file_store.save(db, "u1", "dos.txt", b"2")
