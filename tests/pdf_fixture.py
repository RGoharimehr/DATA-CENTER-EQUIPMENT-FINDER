"""Build a real, minimal PDF on disk.

The PDF tests previously mocked PdfReader and passed a path that did not exist, so
nothing ever exercised actual PDF parsing. This writes a genuine one-page PDF so the
tests read bytes the way the command does.
"""

from __future__ import annotations

from pathlib import Path


def write_text_pdf(path: str | Path, lines: list[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    escaped = [line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)") for line in lines]
    body = "\n".join(f"({line}) Tj 0 -16 Td" for line in escaped)
    content = f"BT /F1 11 Tf 40 750 Td\n{body}\nET".encode("latin-1")

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()

    target.write_bytes(bytes(out))
    return target
