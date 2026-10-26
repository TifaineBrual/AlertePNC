"""Détection des postes PNC et score de pertinence selon le profil."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from veille.models import Offer
from veille.text import has_term, normalize

# --- Détection -------------------------------------------------------------------------------------

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
    category: str = ""  # "pnc", "instructeur_pnc" ou "" (pas un poste PNC)
    term: str = ""
    where: str = ""  # "titre" ou "description"

    @property
    def is_pnc(self) -> bool:
        return self.category == "pnc"


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


# --- Profil ----------------------------------------------------------------------------------------

CEFR = ["a1", "a2", "b1", "b2", "c1", "c2"]


@dataclass
class Profile:
    provided: bool = False
    cca: bool = False
    english_level: str = ""
    english_certified: bool = False
    experience_pnc_months: int = 0
    experience_client_months: int = 0
    bases_ok: list[str] = field(default_factory=list)
    bases_maybe: list[str] = field(default_factory=list)
    contracts_ok: list[str] = field(default_factory=list)
    min_score_to_notify: int = 40


def load_profile(text: str | None) -> Profile:
    """Profil depuis le YAML (secret PROFILE_YAML). Absent ou vide : profil neutre."""
    data = yaml.safe_load(text) if text and text.strip() else None
    if not isinstance(data, dict):
        return Profile()
    known = Profile.__dataclass_fields__.keys() - {"provided"}
    profile = Profile(provided=True, **{k: v for k, v in data.items() if k in known})
    profile.english_level = str(profile.english_level or "").lower()
    return profile


# --- Score -----------------------------------------------------------------------------------------

# Variantes de lieux rencontrées dans les annonces → nom de base tel qu'on l'écrit dans le profil.
PLACE_ALIASES = {
    "roissy": "cdg", "charles de gaulle": "cdg roissy", "tremblay-en-france": "cdg roissy", "tremblay en france": "cdg roissy",
    "villeneuve-le-roi": "orly", "paray-vieille-poste": "orly", "saint-exupery": "lyon", "colombier-saugnieu": "lyon",
    "marignane": "marseille", "cote d'azur": "nice", "gillot": "la reunion", "sainte-marie": "la reunion",
    "saint-denis de la reunion": "la reunion", "reunion": "la reunion", "blagnac": "toulouse", "merignac": "bordeaux",
}
CONTRACT_ALIASES = {
    "fixed term": "cdd", "fixed-term": "cdd", "temporary": "cdd", "permanent": "cdi", "seasonal": "saisonnier",
    "saison": "saisonnier", "apprentissage": "alternance", "apprenti": "alternance", "contrat pro": "contrat de professionnalisation",
}
CONTRACT_WORDS = ["cdi", "cdd", "alternance", "contrat de professionnalisation", "saisonnier", "interim", "stage",
                  "fixed term", "permanent", "seasonal"]
NO_CCA = re.compile(r"sans (le |de )?cca|cca (non|pas) (requis|exige|obligatoire|necessaire)|non titulaires? du cca|\bcqp\b")
NEEDS_CCA = re.compile(r"\bcca\b|cabin crew attestation|attestation (de )?membre d'equipage de cabine")
ENGLISH_LEVEL = re.compile(r"(?:anglais|english)[^.\n]{0,80}?\b([abc][12])\b|\b([abc][12])\b[^.\n]{0,30}?(?:anglais|english)")
TOEIC_SCORE = re.compile(r"toeic[^0-9.\n]{0,40}(\d{3})")
CERTIFICATION = re.compile(r"\b(toeic|linguaskills?|ielts|toefl|bulats)\b")
SHORT_DESCRIPTION = 300

LABELS = [(70, "🟢 Très pertinent"), (40, "🟡 À regarder"), (0, "⚪ Peu pertinent")]


def label_for(value: int) -> str:
    return next(label for threshold, label in LABELS if value >= threshold)


@dataclass
class Score:
    value: int
    reasons: list[str]
    to_check: bool = False

    @property
    def label(self) -> str:
        return label_for(self.value)


def _expand(text: str, aliases: dict[str, str]) -> str:
    text = normalize(text)
    return " ".join([text] + [canon for alias, canon in aliases.items() if alias in text])


def _toeic_to_cefr(points: int) -> str:
    return "c1" if points >= 945 else "b2" if points >= 785 else "b1" if points >= 550 else "a2"


def required_english(text: str) -> str:
    levels = [a or b for a, b in ENGLISH_LEVEL.findall(text)]
    levels += [_toeic_to_cefr(int(p)) for p in TOEIC_SCORE.findall(text)]
    return max(levels, key=CEFR.index, default="")


def score_offer(offer: Offer, detection: Detection, profile: Profile) -> Score:
    reasons = [f"poste PNC détecté ({detection.where} : « {detection.term} »)"]
    value = 50
    to_check = len(offer.description) < SHORT_DESCRIPTION
    if not profile.provided:
        return Score(value, reasons + ["profil non renseigné : score neutre"], to_check)

    # Lieu ; à défaut de lieu, une base peut figurer dans l'intitulé (« Cabin Crew Paris CDG »)
    place = _expand(offer.location or offer.title, PLACE_ALIASES)
    if base := next((b for b in profile.bases_ok if has_term(place, normalize(b))), ""):
        value += 25
        reasons.append(f"+25 base acceptée ({base})")
    elif base := next((b for b in profile.bases_maybe if has_term(place, normalize(b))), ""):
        value += 10
        reasons.append(f"+10 base possible ({base})")
    elif not offer.location:
        value += 5
        reasons.append("+5 lieu non précisé")
    else:
        value -= 20
        reasons.append(f"−20 hors de vos bases ({offer.location})")

    # Contrat
    contract = _expand(offer.contract or " ".join(w for w in CONTRACT_WORDS if has_term(normalize(offer.title), w)), CONTRACT_ALIASES)
    if not contract.strip():
        reasons.append("contrat non précisé")
    elif ok := next((c for c in profile.contracts_ok if has_term(contract, normalize(c))), ""):
        value += 10
        reasons.append(f"+10 contrat {ok}")
    else:
        reasons.append(f"contrat hors préférences ({offer.contract})")

    # Exigences (CCA, anglais) : seulement si l'annonce est assez détaillée pour être évaluée
    text = normalize(f"{offer.title}\n{offer.description}")
    if to_check:
        reasons.append("annonce courte : exigences à vérifier")
    else:
        if not profile.cca:
            if NO_CCA.search(text):
                value += 15
                reasons.append("+15 accessible sans CCA / CQP")
            elif NEEDS_CCA.search(text):
                value -= 30
                reasons.append("−30 CCA exigé")
        required = required_english(text)
        mine = profile.english_level if profile.english_level in CEFR else ""
        if required and mine and CEFR.index(required) > CEFR.index(mine):
            value -= 15
            reasons.append(f"−15 anglais {required.upper()} exigé (vous : {mine.upper()})")
        elif CERTIFICATION.search(text) and not profile.english_certified:
            value -= 15
            reasons.append("−15 certification d'anglais demandée")

    return Score(max(0, min(100, value)), reasons, to_check)
