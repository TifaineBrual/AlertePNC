import pytest

from veille.matching import Profile, detect, label_for, load_profile, required_english, score_offer
from veille.models import Offer
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


def test_instructor_is_classified_apart():
    d = detect("Instructeur PNC H/F")
    assert d.category == "instructeur_pnc" and not d.is_pnc


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


# --- scoring ---

PROFILE = load_profile("""
cca: false
english_level: B2
english_certified: false
bases_ok: ["Paris", "Orly", "Roissy", "CDG"]
bases_maybe: ["Lyon", "Nice", "Marseille", "La Réunion"]
contracts_ok: ["CDI", "CDD", "Alternance", "Contrat de professionnalisation", "Saisonnier"]
min_score_to_notify: 40
""")
LONG = " Missions : accueillir les passagers, assurer la sécurité à bord et le service en vol." * 5


def make(title="Hôtesse de l'air / Steward", location="", contract="", description=""):
    return Offer("test", "Compagnie", "1", title, "https://example.com/1", location=location,
                 contract=contract, description=description)


def score(offer, profile=PROFILE):
    return score_offer(offer, detect(offer.title, offer.description), profile)


def test_no_profile_gives_neutral_score():
    s = score(make(location="Lima", contract="CDI", description="CCA exigé" + LONG), Profile())
    assert s.value == 50 and s.label == "🟡 À regarder"


def test_good_base_and_contract():
    s = score(make(location="45 rue de Paris 95747 ROISSY CHARLES DE GAULLE CEDEX", contract="CDD", description=LONG))
    assert s.value == 85 and s.label == "🟢 Très pertinent"
    assert any("+25" in r for r in s.reasons) and any("+10" in r for r in s.reasons)


def test_alias_tremblay_is_cdg():
    assert any("+25" in r for r in score(make(location="Tremblay-en-France France")).reasons)


def test_maybe_base_unknown_and_outside():
    assert score(make(location="Marignane", description=LONG)).value == 60
    assert score(make(location="", description=LONG)).value == 55
    assert score(make(location="London Gatwick", description=LONG)).value == 30


def test_base_found_in_title_when_no_location():
    assert any("+25" in r for r in score(make(title="Cabin Crew Paris CDG 2027")).reasons)


def test_contract_aliases():
    assert any("+10 contrat CDD" in r for r in score(make(contract="Fixed Term Contract")).reasons)


def test_cca_required_penalty_and_no_cca_bonus():
    assert score(make(description="Titulaire du CCA obligatoire." + LONG)).value == 55 - 30
    assert score(make(description="Recrutement sans CCA : formation CQP prise en charge." + LONG)).value == 55 + 15


def test_english_requirements():
    assert required_english(normalize("Anglais niveau C1 exigé")) == "c1"
    assert required_english(normalize("Score TOEIC de 800 minimum")) == "b2"
    assert score(make(description="Niveau d'anglais C1 requis." + LONG)).value == 55 - 15
    assert score(make(description="Anglais B2 requis." + LONG)).value == 55
    assert score(make(description="TOEIC 750 en cours de validité." + LONG)).value == 55 - 15


def test_short_offer_is_not_penalized_and_flagged():
    s = score(make(description="CCA exigé"))
    assert s.to_check and s.value == 55 and any("à vérifier" in r for r in s.reasons)


def test_labels():
    assert label_for(70) == "🟢 Très pertinent"
    assert label_for(69) == "🟡 À regarder"
    assert label_for(39) == "⚪ Peu pertinent"


def test_example_profile_file_loads():
    from pathlib import Path
    p = load_profile((Path(__file__).parents[1] / "profile.example.yaml").read_text(encoding="utf-8"))
    assert p.provided and p.english_level == "b2" and p.min_score_to_notify == 40
