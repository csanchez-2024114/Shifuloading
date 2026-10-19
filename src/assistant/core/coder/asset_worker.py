"""Reencodeo de imágenes de recursos del codificador en un subproceso aislado.

El proceso padre llama a `reencode(data, kind, timeout)`: lanza `python -I -m assistant.core.coder.asset_worker`
(sin PYTHONPATH, sin site del usuario ni el directorio actual en sys.path), le pasa los bytes por stdin y lee un JSON
por stdout; si tarda más de `timeout` segundos, se mata. Pillow verifica la imagen, la decodifica con tope de
píxeles, la reduce a `max_side` px de lado como máximo y la vuelve a codificar en el mismo formato desde los
píxeles, sin metadatos (EXIF, ICC, comentarios, texto): lo que sobraba en el archivo (p. ej. un script pegado al
final) no sobrevive."""
import base64
import io
import json
import subprocess
import sys

from assistant.core.coder.errors import CoderError

max_side = 2048           # px por lado, como máximo
max_pixels = 40_000_000   # tope de descompresión (más que esto: rechazada)
max_frames = 300          # cuadros de un GIF animado


# ------------------------------------------------------------------ proceso padre
def reencode(data: bytes, kind: str, timeout: float = 20.0) -> dict:
    """{"data": bytes, "width": int, "height": int} o CoderError (asset_too_many_pixels, asset_mismatch,
    asset_timeout)."""
    cmd = [sys.executable, "-I", "-m", "assistant.core.coder.asset_worker", kind]
    try:
        done = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise CoderError("asset_timeout") from exc
    try:
        out = json.loads(done.stdout or b"{}")
    except ValueError:
        out = {}
    if done.returncode != 0 or "b64" not in out:
        raise CoderError("asset_too_many_pixels" if out.get("error") == "too_many_pixels" else "asset_mismatch")
    return {"data": base64.b64decode(out["b64"]), "width": out["width"], "height": out["height"]}


# ------------------------------------------------------------------ subproceso
def _clean(frame):
    frame = frame.copy()
    frame.info = {}  # sin metadatos: nada de exif, icc_profile, comment, text...
    return frame


def run(data: bytes, kind: str) -> dict:
    from PIL import Image, ImageSequence

    Image.MAX_IMAGE_PIXELS = max_pixels
    expected = {"png": "PNG", "jpeg": "JPEG", "gif": "GIF", "webp": "WEBP"}[kind]
    with Image.open(io.BytesIO(data)) as probe:
        if probe.format != expected:
            raise ValueError("format")
        probe.verify()
    img = Image.open(io.BytesIO(data))
    img.load()
    out = io.BytesIO()
    if kind == "gif":
        frames, durations = [], []
        for frame in ImageSequence.Iterator(img):
            durations.append(frame.info.get("duration", 100))
            f = _clean(frame.convert("RGBA"))
            f.thumbnail((max_side, max_side))
            frames.append(f)
            if len(frames) >= max_frames:
                break
        if len(frames) > 1:
            frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:], loop=0,
                           duration=durations[: len(frames)], disposal=2)
        else:  # un solo cuadro: duration debe ser un número, no una lista
            frames[0].save(out, format="GIF")
        width, height = frames[0].size
    else:
        if kind == "jpeg":
            img = img.convert("RGB")
        elif img.mode not in ("RGB", "RGBA", "L", "LA"):
            img = img.convert("RGBA")
        img = _clean(img)
        img.thumbnail((max_side, max_side))
        params = {"quality": 90} if kind in ("jpeg", "webp") else {}
        img.save(out, format=expected, **params)
        width, height = img.size
    return {"b64": base64.b64encode(out.getvalue()).decode(), "width": width, "height": height}


def main() -> int:
    kind = sys.argv[1]
    data = sys.stdin.buffer.read()
    try:
        from PIL import Image

        try:
            result = run(data, kind)
        except Image.DecompressionBombError:
            sys.stdout.write(json.dumps({"error": "too_many_pixels"}))
            return 2
    except Exception:  # noqa: BLE001 - no es una imagen válida del tipo dicho: el padre solo ve "no corresponde"
        sys.stdout.write(json.dumps({"error": "decode_failed"}))
        return 3
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
