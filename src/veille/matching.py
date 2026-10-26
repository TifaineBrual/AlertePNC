"""Détection des postes PNC."""
from __future__ import annotations

import re
from dataclasses import dataclass

from veille.text import has_term, normalize

POSITIVE_TERMS = [
    "pnc", "personnel navigant commercial", "personnel commercial navigant", "personnels navigants commerciaux",
    "hotesse de l'air", "hotesse", "steward", "cabin crew", "flight attendant", "chef de cabine",
    "cqp pnc", "cabin manager", "pnc stagiaire",
]
# Termes trop courts ou ambigus (« PNC », « hôtesse »…) : retenus dans le titre, pas dans la seule description,
# où ils apparaissent souvent en contexte (« en lien avec les PNC »).
DESCRIPTION_TERMS = [t for t in POSITIVE_TERMS if t not in ("pnc", "hotesse", "steward")]
TITLE_EXCLUSIONS = [
    "mecanicien cabine", "planification personnels navigants", "planification personnel navigant",
    "regulation pn", "planning pn", "logistique pn", "support production pn",
    "pilote", "officier pilote", "instructeur", "instructrice", "directeur", "directrice", "stage",
    "hotesse d'accueil", "hote d'accueil", "hotesse de caisse",
]
INSTRUCTOR = re.compile(r"\b(instructeur|instructrice)\b.*\bpnc\b|\bpnc\b.*\b(instructeur|instructrice)\b")


def _first(text: str, terms: list[str]) -> str:
    return next((t for t in terms if has_term(text, t)), "")


@dataclass
class Detection:
    category: str = ""  # "pnc", "instructeur_pnc", "alerte" (source notify_all) ou "" (pas un poste PNC)
    term: str = ""
    where: str = ""  # "titre" ou "description"

    @property
    def is_pnc(self) -> bool:
        return self.category == "pnc"

    @property
    def is_relevant(self) -> bool:
        """À notifier : poste PNC, poste d'instructeur PNC, ou entrée d'une alerte web."""
        return bool(self.category)


ALERT = Detection("alerte", "", "")


def detect(title: str, description: str = "") -> Detection:
    t, d = normalize(title), normalize(description)
    if INSTRUCTOR.search(t):
        return Detection("instructeur_pnc", "instructeur pnc", "titre")
    if _first(t, TITLE_EXCLUSIONS):
        return Detection()
    if term := _first(t, POSITIVE_TERMS):
        return Detection("pnc", term, "titre")
    if term := _first(d, DESCRIPTION_TERMS):
        return Detection("pnc", term, "description")
    return Detection()
