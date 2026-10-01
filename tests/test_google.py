"""L'autorisation Google (spec de Gmail et de Google Agenda, §4 et §7) : le jeton d'accès, les
erreurs dites à David, et `make google`, contre la doublure de Google (doublure_google.py)."""

import subprocess
import threading
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
from doublure_google import ID_CLIENT, JETON_DURABLE, SECRET_CLIENT, DoublureGoogle, repondre

from atlas_core import google
from atlas_core.connecteurs import ErreurConnecteur
from scripts import google as commande

ESSAI = "https://www.googleapis.com/essai/v1/chose"


class Horloge:
    def __init__(self) -> None:
        self.maintenant = 1000.0

    def __call__(self) -> float:
        return self.maintenant


@pytest.fixture
def doublure():
    doublure = DoublureGoogle()
    doublure.route(
        "GET", r"www\.googleapis\.com/essai/v1/chose", lambda r: repondre(200, {"ok": 1})
    )
    return doublure


def autorisation(doublure, horloge=None, jeton=JETON_DURABLE, secret=SECRET_CLIENT):
    return google.Autorisation(
        ID_CLIENT, secret, jeton, http=doublure.http, horloge=horloge or Horloge()
    )


def test_le_jeton_d_acces_se_garde_une_heure_puis_se_renouvelle(doublure):
    horloge = Horloge()
    acces = autorisation(doublure, horloge)

    for _ in range(3):
        assert acces.appeler("GET", ESSAI, service="l'Agenda").json() == {"ok": 1}
    assert doublure.jetons_donnes == 1
    horloge.maintenant += 3599 - 61
    acces.appeler("GET", ESSAI, service="l'Agenda")
    assert doublure.jetons_donnes == 1
    horloge.maintenant += 1
    acces.appeler("GET", ESSAI, service="l'Agenda")
    assert doublure.jetons_donnes == 2, "une minute avant sa fin, il se renouvelle"
    assert doublure.recues[-1].headers["authorization"] == "Bearer acces-2"


def test_plusieurs_requetes_a_la_fois_ne_demandent_qu_un_jeton(doublure):
    # Claude appelle parfois deux outils Google à la fois : un seul jeton, et aucun refusé.
    acces = autorisation(doublure)
    doublure.lenteur_du_jeton = 0.05
    reponses: list[int] = []
    fils = [
        threading.Thread(
            target=lambda: reponses.append(acces.appeler("GET", ESSAI, service="Gmail").status_code)
        )
        for _ in range(6)
    ]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()

    assert (doublure.jetons_donnes, reponses) == (1, [200] * 6)


def test_un_jeton_d_acces_refuse_se_renouvelle_une_fois(doublure):
    acces = autorisation(doublure)
    acces.appeler("GET", ESSAI, service="l'Agenda")
    doublure.retirer_les_acces()

    assert acces.appeler("GET", ESSAI, service="l'Agenda").json() == {"ok": 1}
    assert doublure.jetons_donnes == 2

    doublure.acces_refuses = True
    with pytest.raises(ErreurConnecteur) as refus:
        acces.appeler("GET", ESSAI, service="l'Agenda")
    assert str(refus.value) == google.RETIREE
    assert doublure.jetons_donnes == 3, "une seule nouvelle tentative"


@pytest.mark.parametrize(
    ("panne", "message"),
    [
        ({"jeton": "jeton-retire"}, google.RETIREE),
        ({"secret": "mauvais-secret"}, google.CLIENT_REFUSE),
        (
            {"refus": (403, "accessNotConfigured")},
            "L'accès à Gmail n'est pas activé dans ton projet Google Cloud.",
        ),
        ({"refus": (403, "insufficientPermissions")}, google.PERMISSION),
        ({"refus": (429, "rateLimitExceeded")}, google.MUET),
        ({"refus": (403, "rateLimitExceeded")}, google.MUET),
        ({"refus": (403, "userRateLimitExceeded")}, google.MUET),
        ({"refus": (503, "backendError")}, google.MUET),
        ({"muette": True}, google.MUET),
        ({"jeton_en_panne": 503}, google.MUET),
    ],
)
def test_ce_que_david_peut_reparer_est_dit(doublure, panne, message):
    acces = autorisation(
        doublure, jeton=panne.get("jeton", JETON_DURABLE), secret=panne.get("secret", SECRET_CLIENT)
    )
    doublure.refus = panne.get("refus")
    doublure.muette = panne.get("muette", False)
    doublure.jeton_en_panne = panne.get("jeton_en_panne")

    with pytest.raises(ErreurConnecteur) as refus:
        acces.appeler("GET", ESSAI, service="Gmail")
    assert str(refus.value) == message
    assert SECRET_CLIENT not in str(refus.value) and JETON_DURABLE not in str(refus.value)


def test_un_autre_refus_revient_tel_quel(doublure):
    doublure.refus = (403, "forbidden")

    assert autorisation(doublure).appeler("GET", ESSAI, service="l'Agenda").status_code == 403


@pytest.mark.parametrize(
    ("raison", "message"),
    [
        ("SERVICE_DISABLED", "L'accès à Gmail n'est pas activé dans ton projet Google Cloud."),
        ("ACCESS_TOKEN_SCOPE_INSUFFICIENT", google.PERMISSION),
    ],
)
def test_le_format_d_erreur_recent_de_google(doublure, raison, message):
    # Les API récentes de Google disent la raison dans `details` (google.rpc.ErrorInfo).
    detail = {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": raison}
    refus = {"error": {"code": 403, "status": "PERMISSION_DENIED", "details": [detail]}}
    doublure.route("GET", r"www\.googleapis\.com/essai/v1/recent", lambda r: repondre(403, refus))

    with pytest.raises(ErreurConnecteur) as dit:
        autorisation(doublure).appeler(
            "GET", "https://www.googleapis.com/essai/v1/recent", service="Gmail"
        )
    assert str(dit.value) == message


def test_google_muet_en_cours_de_route(doublure):
    acces = autorisation(doublure)
    acces.appeler("GET", ESSAI, service="Gmail")
    doublure.muette = True

    with pytest.raises(ErreurConnecteur) as refus:
        acces.appeler("GET", ESSAI, service="Gmail")
    assert str(refus.value) == google.MUET


def navigateur(doublure, reponse=None):
    """Le navigateur de David : il ouvre la page de Google, David accepte, et Google le renvoie
    vers le petit serveur de `make google`, avec le code (ou ce que `reponse` en fait)."""
    ouvertes: list[str] = []

    def ouvrir(adresse: str) -> None:
        ouvertes.append(adresse)
        accord = doublure.accorder(adresse)
        retour = accord.pop("retour")
        params = accord if reponse is None else reponse(accord)

        def page() -> None:  # le navigateur demande aussi son icône
            ouvertes.append(f"favicon.ico : {httpx.get(retour + 'favicon.ico').status_code}")
            ouvertes.append(httpx.get(retour, params=params).text)

        threading.Thread(target=page).start()

    return ouvrir, ouvertes


def test_make_google_obtient_le_jeton_durable(doublure):
    ouvrir, ouvertes = navigateur(doublure)

    jeton = google.connecter(ID_CLIENT, SECRET_CLIENT, http=doublure.http, ouvrir=ouvrir)

    assert jeton == "jeton-durable-2" and jeton in doublure.jetons_durables
    demande = dict(parse_qsl(urlsplit(ouvertes[0]).query))
    assert ouvertes[0].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert demande["redirect_uri"].startswith("http://127.0.0.1:")
    assert set(demande["scope"].split()) == set(google.PERMISSIONS)
    assert (demande["access_type"], demande["prompt"], demande["code_challenge_method"]) == (
        "offline",
        "consent",
        "S256",
    )
    [echange] = [r for r in doublure.recues if r.url.host == "oauth2.googleapis.com"]
    assert b"code_verifier=" in echange.content, "PKCE : le secret de la commande"
    assert "favicon.ico : 404" in ouvertes, "le petit serveur n'attend que la réponse de Google"


@pytest.mark.parametrize(
    ("reponse", "message"),
    [
        (lambda accord: {**accord, "state": "une-autre-demande"}, google.AUTRE_DEMANDE),
        (lambda accord: {"error": "access_denied", "state": accord["state"]}, google.PAS_AUTORISE),
    ],
)
def test_make_google_refuse_une_reponse_detournee_ou_un_refus(doublure, reponse, message):
    ouvrir, _ = navigateur(doublure, reponse)

    with pytest.raises(google.ErreurConnexion) as refus:
        google.connecter(ID_CLIENT, SECRET_CLIENT, http=doublure.http, ouvrir=ouvrir)
    assert str(refus.value) == message


def test_make_google_avec_un_secret_refuse_ou_google_en_panne(doublure):
    ouvrir, _ = navigateur(doublure)
    with pytest.raises(google.ErreurConnexion) as refus:
        google.connecter(ID_CLIENT, "mauvais-secret", http=doublure.http, ouvrir=ouvrir)
    assert str(refus.value) == google.CLIENT_REFUSE

    doublure.jeton_en_panne = 503
    ouvrir, _ = navigateur(doublure)
    with pytest.raises(google.ErreurConnexion) as refus:
        google.connecter(ID_CLIENT, SECRET_CLIENT, http=doublure.http, ouvrir=ouvrir)
    assert str(refus.value) == google.MUET


def test_make_google_sans_reponse_abandonne(doublure):
    with pytest.raises(google.ErreurConnexion) as refus:
        google.connecter(
            ID_CLIENT, SECRET_CLIENT, http=doublure.http, ouvrir=lambda adresse: None, attente_s=0.2
        )
    assert str(refus.value) == google.SANS_REPONSE


def test_make_google_ecrit_le_jeton_dans_le_env_et_l_affiche_sur_demande(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ATLAS_GOOGLE_ID_CLIENT=client\n")
    dits: list[str] = []
    environ = {"ATLAS_GOOGLE_ID_CLIENT": "client", "ATLAS_GOOGLE_SECRET_CLIENT": "secret"}

    assert (
        commande.main(environ, fichier_env=env, obtenir=lambda i, s: "jeton-neuf", dire=dits.append)
        == 0
    )
    assert env.read_text() == "ATLAS_GOOGLE_ID_CLIENT=client\nATLAS_GOOGLE_JETON=jeton-neuf\n"
    assert "jeton-neuf" not in " ".join(dits), "affiché seulement sur demande"
    commande.main(
        {**environ, "AFFICHER": "1"},
        fichier_env=env,
        obtenir=lambda i, s: "jeton-neuf",
        dire=dits.append,
    )
    assert dits[-1] == "jeton-neuf"


def test_make_google_sans_client_ou_refuse(tmp_path):
    dits: list[str] = []

    def jamais(id_client, secret):
        raise AssertionError("sans son client, make google ne contacte pas Google")

    for sans in ({}, {"ATLAS_GOOGLE_ID_CLIENT": "c"}):
        fin = commande.main(sans, fichier_env=tmp_path / ".env", obtenir=jamais, dire=dits.append)
        assert fin == 1
    assert dits == [commande.MANQUE, commande.MANQUE]

    def refuse(id_client, secret):
        raise google.ErreurConnexion(google.PAS_AUTORISE)

    environ = {"ATLAS_GOOGLE_ID_CLIENT": "c", "ATLAS_GOOGLE_SECRET_CLIENT": "s"}
    assert (
        commande.main(environ, fichier_env=tmp_path / ".env", obtenir=refuse, dire=dits.append) == 1
    )
    assert dits[-1] == google.PAS_AUTORISE and not (tmp_path / ".env").exists()


def test_la_cible_make_google_lance_la_connexion():
    sortie = subprocess.run(["make", "-n", "google"], capture_output=True, text=True, check=True)
    assert "python -m scripts.google" in sortie.stdout
