"""Shared overlay text-fitting rules (mirrored by plugin/src/ui/overlay.ts).

Kept in one place conceptually: the plugin and this preview must agree, otherwise
the preview would flatter the reader. Widths are estimated rather than measured
so that the same numbers can be produced in the plugin's shadow DOM without a
canvas, and in Python without a font metrics dependency.
"""

from __future__ import annotations

MIN_FONT = 5.0
MAX_FONT = 20.0
LINE_HEIGHT = 1.16
# Average glyph advance as a fraction of the font size.
CJK_WIDTH = 1.0
LATIN_WIDTH = 0.55
SPACE_WIDTH = 0.3
NARROW = set("iljI.,:;'|!()[]{}/")
WIDE = set("mwMW@%")
PUNCT_CJK = set("（）【】《》“”‘’，。、；：！？·—…")
# Characters that must not begin a line (CJK typesetting rule).
NO_LINE_START = set("，。、；：！？）》”』】·…％‰℃")
NO_LINE_END = set("（《“‘『【")


def char_width(char: str) -> float:
    if char in PUNCT_CJK or "\u4e00" <= char <= "\u9fff" or "\u3000" <= char <= "\u303f":
        return CJK_WIDTH
    if char == " ":
        return SPACE_WIDTH
    if char in NARROW:
        return LATIN_WIDTH * 0.55
    if char in WIDE:
        return LATIN_WIDTH * 1.45
    if "\u0400" <= char <= "\u04ff":
        return LATIN_WIDTH
    return LATIN_WIDTH


def _is_latin(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char in "-_+./%()[]")


def wrap_estimated(text: str, font_size: float, width: float) -> list[str]:
    """Greedy wrap: never split a Latin word, always allow a CJK break.

    ``width`` is in pixels and every advance below is converted to pixels, so the
    em-relative character widths above and the wrap limit stay in the same unit.
    """
    limit = width
    lines: list[str] = []
    current: list[str] = []
    current_width = 0.0
    index = 0
    length = len(text)

    def flush() -> None:
        nonlocal current, current_width
        if current:
            lines.append("".join(current).rstrip())
        current, current_width = [], 0.0

    while index < length:
        char = text[index]
        if char == "\n":
            flush()
            index += 1
            continue
        # Keep Latin runs (words, numbers, identifiers) together.
        if _is_latin(char):
            end = index
            while end < length and _is_latin(text[end]):
                end += 1
            word = text[index:end]
            word_width = sum(char_width(c) for c in word) * font_size
            if current_width + word_width > limit and current:
                flush()
            if word_width > limit and not current:
                # A single very long token: allow a hard break.
                for piece in word:
                    if current_width + char_width(piece) * font_size > limit and current:
                        flush()
                    current.append(piece)
                    current_width += char_width(piece) * font_size
                index = end
                continue
            current.append(word)
            current_width += word_width
            index = end
            continue
        advance = char_width(char) * font_size
        if current_width + advance > limit and current:
            flush()
        current.append(char)
        current_width += advance
        index += 1
    flush()
    return _apply_kinsoku(lines)


def _apply_kinsoku(lines: list[str]) -> list[str]:
    """Keep closing punctuation off the start of a line, and opening off the end."""
    for index in range(1, len(lines)):
        while lines[index] and lines[index][0] in NO_LINE_START:
            lines[index - 1] += lines[index][0]
            lines[index] = lines[index][1:]
    return [line for line in lines if line]


def fits(lines: list[str], font_size: float, height: float, width: float) -> bool:
    if not lines:
        return True
    needed = len(lines) * font_size * LINE_HEIGHT
    if needed > height + 0.5:
        return False
    # A glyph wider than the box would be clipped horizontally.
    widest = max(sum(char_width(c) for c in line) * font_size for line in lines)
    return widest <= width + 1.5


def fit_font_size(text: str, width: float, height: float) -> float | None:
    """Largest font size at which the whole translation fits inside the box.

    Returns None when even the minimum size does not fit, so the caller can skip
    the overlay instead of drawing a truncated paragraph. Truncated sentences are
    worse than a visible gap: the reader cannot tell that text is missing.
    """
    if width < 12 or height < 5:
        return None
    preferred = max(MIN_FONT, min(MAX_FONT, height * 0.9))
    size = round(preferred * 2) / 2
    while size >= MIN_FONT:
        lines = wrap_estimated(text, size, width - 2)
        if fits(lines, size, height - 1, width - 2):
            return round(size, 1)
        size -= 0.5
    return None
