"""Archivos de prueba para las evals y los tests de FILES_ENABLED, generados en memoria con datos inventados."""
import io


def pdf_bytes(text: str) -> bytes:
    """PDF mínimo de una página con `text`, armado a mano (sin dependencias para escribirlo)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


def png_square(color: tuple[int, int, int], size: int = 400) -> bytes:
    """Imagen de un cuadrado de un color sobre fondo blanco."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (size, size), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([size // 4, size // 4, 3 * size // 4, 3 * size // 4], fill=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build(spec: dict) -> tuple[str, bytes]:
    """(nombre, bytes) de un paso "upload" del dataset: {"name", "text"} | {"name", "pdf_text"} |
    {"name", "png_color": [r, g, b]} | {"name", "raw": texto que no corresponde a la extensión}."""
    name = spec["name"]
    if "pdf_text" in spec:
        return name, pdf_bytes(spec["pdf_text"])
    if "png_color" in spec:
        return name, png_square(tuple(spec["png_color"]))
    return name, (spec.get("text") or spec.get("raw") or "").encode("utf-8")
