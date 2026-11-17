"""Generate tiny valid PDFs for tests without third-party PDF writers."""

from __future__ import annotations

from pathlib import Path

PAGE_W, PAGE_H = 612, 792


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content(lines: list[tuple[float, float, float, str]]) -> str:
    parts = ["BT", "1 0 0 1 0 0 Tm"]
    current_size = None
    for x, y, size, text in lines:
        if size != current_size:
            parts.append(f"/F1 {size} Tf")
            current_size = size
        parts.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
        parts.append(f"({_escape(text)}) Tj")
    parts.append("ET")
    return "\n".join(parts)


def make_pdf(path: Path, pages: list[list[tuple[float, float, float, str]]]) -> Path:
    """pages: list of pages, each a list of (x, y, fontsize, text)."""
    objects: list[bytes] = []

    def add(obj: str) -> int:
        objects.append(obj.encode("latin-1"))
        return len(objects)

    catalog = add("<< /Type /Catalog /Pages 2 0 R >>")
    pages_obj = add("<< /Type /Pages /Kids [] /Count 0 >>")
    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    kids: list[str] = []
    for page_lines in pages:
        content = _content(page_lines)
        content_obj = add(
            f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}\nendstream"
        )
        page_obj = add(
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content_obj} 0 R >>"
        )
        kids.append(f"{page_obj} 0 R")
    objects[pages_obj - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode(
            "latin-1"
        )
    )
    objects[catalog - 1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    path.write_bytes(bytes(out))
    return path


def body_page(
    paragraphs: list[str], *, start_y: float = 700.0
) -> list[tuple[float, float, float, str]]:
    lines: list[tuple[float, float, float, str]] = []
    y = start_y
    for paragraph in paragraphs:
        for line in _wrap(paragraph, 88):
            lines.append((72.0, y, 10.0, line))
            y -= 13.0
        y -= 12.0
    return lines


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def paper_pdf(
    path: Path,
    *,
    pages: int = 2,
    title: str = "Looming Attention for Efficient Retrieval",
) -> Path:
    content: list[list[tuple[float, float, float, str]]] = []
    first = [(72.0, 740.0, 16.0, title)]
    first += body_page(
        [
            "Abstract. We study efficient retrieval augmented generation for long scientific documents.",
            "We propose LoomAttention, a sparse attention mechanism that reduces memory by 42% while preserving accuracy.",
            "Experiments on three benchmarks show consistent gains over strong baselines.",
        ],
        start_y=700.0,
    )
    content.append(first)
    for page in range(2, pages + 1):
        content.append(
            body_page(
                [
                    f"We describe the method in detail on page {page} of this synthetic paper.",
                    "Our approach combines block sparse attention with a learned routing network.",
                    "The routing network selects key blocks using a lightweight scoring function.",
                ],
                start_y=720.0,
            )
        )
    return make_pdf(path, content)


def two_column_pdf(path: Path) -> Path:
    page: list[tuple[float, float, float, str]] = [
        (72.0, 740.0, 14.0, "A Two Column Paper")
    ]
    for index in range(8):
        page.append(
            (72.0, 700.0 - index * 14, 10.0, f"Left column line {index} keeps talking.")
        )
        page.append(
            (330.0, 700.0 - index * 14, 10.0, f"Right column line {index} is separate.")
        )
    return make_pdf(path, [page])


def scanned_pdf(path: Path) -> Path:
    return make_pdf(path, [[]])
