"""Characters outside the expected scripts in stored model text (Bhargavi, 2026-10-22).

Model answers are English. On the final WG demo run Ultra ended a chain description with "互"
(U+4E92) and Super ended a finding's consequence with "水。", both with `finish_reason: stop`.
Such a character is named on the card by its code point; the text is never altered (CLAUDE.md
§3: model output is never edited in place).

The expected scripts are the Unicode blocks below; anything else is flagged.
"""

from collections.abc import Iterable

# (first, last) code point of each expected block
EXPECTED_BLOCKS = (
    (0x0009, 0x000D),  # tab, line feed and the other whitespace controls
    (0x0020, 0x007E),  # Basic Latin
    (0x00A0, 0x00FF),  # Latin-1 Supplement: accents, °, ×, ±, µ, ½
    (0x0100, 0x024F),  # Latin Extended-A and -B
    (0x0370, 0x03FF),  # Greek and Coptic: Δ, μ
    (0x2000, 0x206F),  # General Punctuation: dashes, the non-breaking hyphen, quotes, …
    (0x2070, 0x209F),  # Superscripts and Subscripts: 10⁻⁴
    (0x20A0, 0x20CF),  # Currency Symbols
    (0x2100, 0x214F),  # Letterlike Symbols
    (0x2150, 0x218F),  # Number Forms
    (0x2190, 0x21FF),  # Arrows
    (0x2200, 0x22FF),  # Mathematical Operators: ≥, ≈
    (0x2300, 0x23FF),  # Miscellaneous Technical
)
FLAG = "unexpected character in model text: {code} ({field})"


def _expected(char: str) -> bool:
    point = ord(char)
    return any(first <= point <= last for first, last in EXPECTED_BLOCKS)


def unexpected_characters(text: str) -> list[str]:
    """Each unexpected character's code point (`U+4E92`), once, in the order it appears."""
    found = (f"U+{ord(c):04X}" for c in text if not _expected(c))
    return list(dict.fromkeys(found))


def unexpected_flags(fields: Iterable[tuple[str, str | None]]) -> list[str]:
    """One flag per unexpected character per field, given (field label, text) pairs."""
    return [
        FLAG.format(code=code, field=label)
        for label, text in fields
        if text
        for code in unexpected_characters(text)
    ]
