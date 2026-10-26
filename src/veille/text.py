from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup

_SPACES = re.compile(r"\s+")
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'", " ": " "})


def normalize(text: str) -> str:
    """Minuscules, sans accents, apostrophes et espaces unifiés."""
    text = unicodedata.normalize("NFKD", (text or "").translate(_APOSTROPHES))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _SPACES.sub(" ", text.lower()).strip()


def has_term(normalized_text: str, normalized_term: str) -> bool:
    """Le terme apparaît-il comme mot (ou groupe de mots) entier ?"""
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", normalized_text) is not None


def html_to_text(html: str, sep: str = "\n") -> str:
    """Texte brut d'un fragment HTML ; `sep` est inséré entre les nœuds texte."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return clean_lines(soup.get_text(sep))


def clean_lines(text: str) -> str:
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def excerpt(text: str, limit: int = 300) -> str:
    text = _SPACES.sub(" ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
