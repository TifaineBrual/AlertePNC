import pytest

from veille.matching import detect
from veille.text import normalize

PNC_TITLES = [
    "Hôtesse de l'air / Steward H/F",
    "PNC – Personnel Navigant Commercial (CDD saison été 2027)",
    "Personnel Commercial Navigant H/F",
    "Personnels Navigants Commerciaux (PNC) - Candidature spontanée H/F",
    "Cabin Crew Paris CDG 2027 - Fixed Term Contract",
    "Flight Attendant - Orly base",
    "Chef de Cabine Principal H/F",
    "Formation CQP PNC – promotion mars",
    "Cabin Manager",
    "PNC stagiaire - contrat de professionnalisation",
    "Steward",
]

# Faux positifs rencontrés pendant l'audit, plus les exclusions génériques du brief.
NOT_PNC_TITLES = [
    "Mécanicien cabine F/H",                                                # Air France
    "Chargé de planification Personnels Navigants (H/F)",                  # Air Corsica
    "Stage - Chargé de projet Outils & Méthodes Régulation PN H/F",        # Transavia
    "Stage - Chargé de projet Outils & Méthodes Planification  PN (H/F)",  # Transavia
    "Stage - Analyste Outils & Méthodes Logistique PN H/F",                # Transavia
    "Responsable Support Production PN H/F",                               # Transavia
    "Agent Planning PN H/F",
    "Régulation PN - agent de nuit",
    "Pilote de ligne F/H",
    "Officier Pilote de Ligne A320",
    "B737 First Officer short haul Pilot opportunities ASLB",
    "Directeur des opérations PNC",
    "Stage - Assistant PNC",
    "Hôtesse d'accueil salon H/F",
    "Ingénieur Planification de Maintenance H/F",
    "Représentant commercial H/F",
]


@pytest.mark.parametrize("title", PNC_TITLES)
def test_pnc_titles_detected(title):
    assert detect(title).is_pnc, title


@pytest.mark.parametrize("title", NOT_PNC_TITLES)
def test_false_positives_excluded(title):
    assert not detect(title).is_pnc, title


def test_instructor_is_classified_apart_but_notified():
    d = detect("Instructeur PNC H/F")
    assert d.category == "instructeur_pnc" and not d.is_pnc and d.is_relevant


def test_description_match_needs_explicit_term():
    assert detect("Agent d'escale", "Vous travaillerez en lien avec les PNC et les pilotes.").category == ""
    d = detect("Recrutement saison 2027", "Nous recrutons du personnel navigant commercial pour l'été.")
    assert d.is_pnc and d.where == "description"


def test_exclusion_in_title_wins_over_description():
    assert not detect("Pilote de ligne", "Cabin crew et personnel navigant commercial à bord").is_pnc


def test_stagiaire_is_not_stage():
    assert detect("PNC Stagiaire").is_pnc


def test_normalize_accents_and_apostrophes():
    assert normalize("Hôtesse de l’Air  ÉTÉ") == "hotesse de l'air ete"
