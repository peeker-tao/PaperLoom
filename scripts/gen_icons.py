"""Generate plugin icons (no external dependencies)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

BG = (35, 97, 90)
PAGE_BACK = (157, 191, 182)
PAGE_FRONT = (251, 250, 247)
LINE = (35, 97, 90, 120)
DESIGN = 96.0


def _rounded_rect(x, y, w, h, r):
    if r <= 0:
        return lambda px, py: x <= px <= x + w and y <= py <= y + h
    return lambda px, py: (
        x <= px <= x + w
        and y <= py <= y + h
        and (
            (px - (x + r)) ** 2 + (py - (y + r)) ** 2 >= r * r
            if px < x + r and py < y + r
            else True
        )
        and (
            (px - (x + w - r)) ** 2 + (py - (y + r)) ** 2 >= r * r
            if px > x + w - r and py < y + r
            else True
        )
        and (
            (px - (x + r)) ** 2 + (py - (y + h - r)) ** 2 >= r * r
            if px < x + r and py > y + h - r
            else True
        )
        and (
            (px - (x + w - r)) ** 2 + (py - (y + h - r)) ** 2 >= r * r
            if px > x + w - r and py > y + h - r
            else True
        )
    )


def render(size: int) -> bytes:
    scale = size / DESIGN
    ss = 3
    width = height = size
    canvas = [[(0, 0, 0, 0)] * width for _ in range(height)]

    shapes = [
        (_rounded_rect(2, 2, 92, 92, 20), (BG[0], BG[1], BG[2], 255)),
        (
            _rounded_rect(40, 18, 36, 48, 3),
            (PAGE_BACK[0], PAGE_BACK[1], PAGE_BACK[2], 255),
        ),
        (
            _rounded_rect(22, 26, 38, 50, 3),
            (PAGE_FRONT[0], PAGE_FRONT[1], PAGE_FRONT[2], 255),
        ),
    ]
    for index in range(4):
        shapes.append(
            (_rounded_rect(28, 38 + index * 8, 26 - index * 3, 2.6, 1.2), LINE)
        )

    for py in range(height):
        for px in range(width):
            r = g = b = a = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    dx = (px + (sx + 0.5) / ss) / scale
                    dy = (py + (sy + 0.5) / ss) / scale
                    cover = (0, 0, 0, 0)
                    for predicate, color in shapes:
                        if predicate(dx, dy):
                            cover = color
                    r += cover[0] * cover[3] / 255
                    g += cover[1] * cover[3] / 255
                    b += cover[2] * cover[3] / 255
                    a += cover[3]
            total = ss * ss
            if a == 0:
                canvas[py][px] = (0, 0, 0, 0)
            else:
                canvas[py][px] = (
                    int(r * 255 / a + 0.5),
                    int(g * 255 / a + 0.5),
                    int(b * 255 / a + 0.5),
                    int(a / total + 0.5),
                )
    raw = bytearray()
    for row in canvas:
        raw.append(0)
        for pixel in row:
            raw.extend(pixel)
    return _png(width, height, bytes(raw))


def _png(width: int, height: int, raw: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    icons = Path(__file__).resolve().parents[1] / "plugin" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    (icons / "icon.png").write_bytes(render(48))
    (icons / "icon@2x.png").write_bytes(render(96))
    print(f"icons written to {icons}")


if __name__ == "__main__":
    main()
