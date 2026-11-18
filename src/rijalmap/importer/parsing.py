"""Pure parsing helpers for the two Kaggle files. No database here, so they are easy to test."""
import math
import re

_YEAR_RE = re.compile(r"(\d{1,4})\s*(BH|AH)\b")
_CE_RE = re.compile(r"\d{1,4}\s*CE\b")


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def parse_id_list(value) -> list[int]:
    """'1, 2, 3' -> [1, 2, 3]. Missing -> []. Anything that is not a number (e.g. 'others') is ignored."""
    if _is_missing(value):
        return []
    if isinstance(value, (int, float)):
        return [int(value)]
    return [int(x) for x in re.findall(r"\d+", str(value))]


def parse_hijri_year(*texts) -> int | None:
    """Find the first '<n> BH' or '<n> AH' in the given texts. BH becomes a negative year.

    The numeric *_hijri columns in the dataset lose the BH sign (the Prophet's birth is stored as 53),
    so years must be read from the text columns instead.
    """
    for text in texts:
        if _is_missing(text):
            continue
        match = _YEAR_RE.search(str(text))
        if match:
            year = int(match.group(1))
            return -year if match.group(2) == "BH" else year
    return None


def has_ce_only(*texts) -> bool:
    """True when a date is written only in the Gregorian calendar (we do not convert those)."""
    joined = " ".join(str(t) for t in texts if not _is_missing(t))
    return bool(_CE_RE.search(joined)) and not _YEAR_RE.search(joined)


def parse_death_year(death_date_place, death_date_hijri) -> int | None:
    """Death years are always AH. Prefer the text; fall back to the numeric column."""
    year = parse_hijri_year(death_date_place)
    if year is not None:
        return year
    if not _is_missing(death_date_hijri):
        try:
            return int(float(death_date_hijri))
        except ValueError:
            return None
    return None


def clean_hadith_no(value) -> str | None:
    """Strip whitespace. Return None for junk values that contain no digit (the dataset has rows like '\\nGrade')."""
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text if re.search(r"\d", text) else None
