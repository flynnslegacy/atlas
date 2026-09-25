"""Le cerveau Claude, sans appeler Claude : une doublure du client SDK rejoue des
messages réalistes (deltas de texte, appel à la recherche web, message de fin, erreurs)."""

import asyncio
import dataclasses
import datetime as dt

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    CLINotFoundError,
    ProcessError,
    RateLimitEvent,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import RateLimitInfo

from atlas_core import cerveau_claude
from atlas_core.cerveau import RECHERCHE, ErreurCerveau
from atlas_core.cerveau_claude import (
    ABSENT,
    ARRET,
    DECONNECTE,
    INJOIGNABLE,
    LIMITE,
    PHRASE_FIL_PERDU,
    CerveauClaude,
    options_cerveau,
    purger_cles_api,
)
from atlas_core.consignes import CONSIGNES

MOMENT = dt.datetime(2026, 9, 24, 21, 50)

# --- messages du SDK --------------------------------------------------------


def _evenement(event: dict, parent: str | None = None) -> StreamEvent:
    return StreamEvent(uuid="u", session_id="s", event=event, parent_tool_use_id=parent)


def debut_texte() -> StreamEvent:
    return _evenement({"type": "content_block_start", "content_block": {"type": "text"}})


def delta(texte: str, parent: str | None = None) -> StreamEvent:
    return _evenement(
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": texte}}, parent
    )


def debut_recherche(identifiant: str = "t1") -> StreamEvent:
    bloc = {"type": "tool_use", "name": "WebSearch", "id": identifiant, "input": {}}
    return _evenement({"type": "content_block_start", "content_block": bloc})


def appel_recherche(identifiant: str = "t1") -> AssistantMessage:
    bloc = ToolUseBlock(id=identifiant, name="WebSearch", input={"query": "météo"})
    return AssistantMessage(content=[bloc], model="claude-sonnet-5")


def erreur_assistant(code: str, texte: str = "API Error") -> AssistantMessage:
    return AssistantMessage(content=[TextBlock(text=texte)], model="claude-sonnet-5", error=code)


def limite(statut: str) -> RateLimitEvent:
    return RateLimitEvent(rate_limit_info=RateLimitInfo(status=statut), uuid="u", session_id="s")


def fin(**champs) -> ResultMessage:
    valeurs = dict(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s",
    )
    valeurs.update(champs)
    return ResultMessage(**valeurs)


def reponse(*morceaux: str) -> list:
    return [debut_texte(), *(delta(m) for m in morceaux), fin()]


BLOQUE = object()  # Claude réfléchit encore : plus rien n'arrive avant une interruption


# --- la doublure du client SDK -------------------------------------------------


class FauxClientClaude:
    """Rejoue un tour de messages par question posée."""

    def __init__(self, *tours: list, journal: list | None = None) -> None:
        self.tours = list(tours)
        self.questions: list[str] = []
        self.journal = journal if journal is not None else []
        self.connexions = 0
        self.interruptions = 0
        self.deconnexions = 0
        self.echec_connexion: BaseException | None = None
        self.echec_question: BaseException | None = None
        self.interruption_sans_effet = False
        self._tour: list = []
        self._reveil = asyncio.Event()
        self._en_attente_du_reveil = False  # Claude n'a encore rien produit de plus

    async def connect(self) -> None:
        if self.echec_connexion is not None:
            raise self.echec_connexion
        self.connexions += 1
        self.journal.append("connexion")

    async def query(self, prompt: str) -> None:
        if self.echec_question is not None:
            raise self.echec_question
        self.questions.append(prompt)
        self.journal.append("question")
        self._tour = list(self.tours.pop(0))
        self._reveil = asyncio.Event()

    async def receive_response(self):
        while self._tour:
            message = self._tour.pop(0)
            if message is BLOQUE:
                self._en_attente_du_reveil = True
                try:
                    await self._reveil.wait()
                finally:
                    self._en_attente_du_reveil = False
                continue
            if isinstance(message, BaseException):
                raise message
            yield message
            if isinstance(message, ResultMessage):
                return
            await asyncio.sleep(0)

    async def interrupt(self) -> None:
        self.interruptions += 1
        self.journal.append("interruption")
        if self.interruption_sans_effet:
            return
        # Comme le vrai CLI (au plus 100 messages en attente) : la réponse à
        # l'interruption arrive derrière tout ce qui était déjà en file, donc
        # seulement une fois que `receive_response` l'a lu. On guette aussi, à
        # chaque tour, le moment où le lecteur s'arrête sur `BLOQUE` (Claude n'a
        # encore rien produit de plus) : le tour s'arrête alors net, et son
        # message de fin arrive quand même, comme le ferait le CLI.
        while self._tour:
            if self._en_attente_du_reveil:
                self._tour = [fin(subtype="error_during_execution", is_error=True)]
                self._reveil.set()
            await asyncio.sleep(0)

    async def disconnect(self) -> None:
        self.deconnexions += 1
        self.journal.append("deconnexion")


class Fabrique:
    def __init__(self, *clients: FauxClientClaude) -> None:
        self.clients = list(clients)
        self.creations = 0

    def __call__(self) -> FauxClientClaude:
        self.creations += 1
        return self.clients.pop(0)


class Temps:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _cerveau(*clients: FauxClientClaude, temps: Temps | None = None) -> CerveauClaude:
    return CerveauClaude(
        Fabrique(*clients), oubli_s=30 * 60, horloge=temps or Temps(), maintenant=lambda: MOMENT
    )


async def _tout(cerveau: CerveauClaude, texte: str) -> list:
    async def lire() -> list:
        return [f async for f in cerveau.repondre(texte)]

    # Garde-fou : un cerveau qui attend à tort échoue au lieu de bloquer la suite.
    return await asyncio.wait_for(lire(), timeout=2)


# --- le texte ----------------------------------------------------------------


async def test_le_texte_arrive_au_fil_des_mots():
    cerveau = _cerveau(FauxClientClaude(reponse("Il est ", "midi ", "dix.")))
    assert await _tout(cerveau, "Quelle heure est-il ?") == ["Il est ", "midi ", "dix."]


async def test_chaque_question_part_avec_la_ligne_de_date():
    client = FauxClientClaude(reponse("Oui."))
    await _tout(_cerveau(client), "Tu m'entends ?")
    assert client.questions == ["[jeudi 24 septembre 2026, 21 h 50]\nTu m'entends ?"]


async def test_le_client_ne_demarre_qu_a_la_premiere_question_puis_reste_allume():
    client = FauxClientClaude(reponse("Un."), reponse("Deux."))
    fabrique = Fabrique(client)
    cerveau = CerveauClaude(fabrique, maintenant=lambda: MOMENT)
    assert fabrique.creations == 0, "un Core sans Claude doit démarrer quand même"

    assert await _tout(cerveau, "un") == ["Un."]
    assert await _tout(cerveau, "deux") == ["Deux."]
    assert (fabrique.creations, client.connexions) == (1, 1)


async def test_les_evenements_d_un_sous_agent_sont_ignores():
    client = FauxClientClaude([debut_texte(), delta("caché", parent="t9"), delta("Vu."), fin()])
    assert await _tout(_cerveau(client), "q") == ["Vu."]


async def test_deux_blocs_de_texte_sont_separes_par_une_espace():
    tour = [debut_texte(), delta("Voyons."), debut_texte(), delta("D'après Météo-France."), fin()]
    fragments = await _tout(_cerveau(FauxClientClaude(tour)), "q")
    assert "".join(fragments) == "Voyons. D'après Météo-France."


# --- la recherche web ----------------------------------------------------------


async def test_une_recherche_web_est_signalee_une_seule_fois():
    tour = [debut_recherche("t1"), appel_recherche("t1"), debut_texte(), delta("Il pleut."), fin()]
    assert await _tout(_cerveau(FauxClientClaude(tour)), "Il pleut ?") == [RECHERCHE, "Il pleut."]


async def test_deux_recherches_distinctes_sont_signalees_deux_fois():
    tour = [debut_recherche("t1"), debut_recherche("t2"), debut_texte(), delta("Oui."), fin()]
    fragments = await _tout(_cerveau(FauxClientClaude(tour)), "q")
    assert fragments.count(RECHERCHE) == 2


async def test_une_recherche_vue_seulement_dans_le_message_complet_est_signalee():
    tour = [appel_recherche("t1"), debut_texte(), delta("Oui."), fin()]
    assert await _tout(_cerveau(FauxClientClaude(tour)), "q") == [RECHERCHE, "Oui."]


# --- l'interruption --------------------------------------------------------------


async def test_une_reponse_abandonnee_est_interrompue_et_videe_avant_la_suivante():
    journal: list = []
    client = FauxClientClaude(
        [debut_texte(), delta("Une très longue "), BLOQUE, delta("jamais lu"), fin()],
        reponse("Oui ?"),
        journal=journal,
    )
    cerveau = _cerveau(client)

    flux = cerveau.repondre("Raconte.")
    assert await anext(flux) == "Une très longue "
    await flux.aclose()  # la session lâche la réponse (barge-in, question tapée…)

    assert await _tout(cerveau, "Attends.") == ["Oui ?"]
    assert journal == ["connexion", "question", "interruption", "question"]


async def test_la_session_n_attend_pas_le_menage_pour_lacher_la_reponse(monkeypatch):
    monkeypatch.setattr(cerveau_claude, "DELAI_MENAGE_S", 0.05)
    client = FauxClientClaude([debut_texte(), delta("Long "), BLOQUE], reponse("Oui."))
    client.interruption_sans_effet = True  # Claude tarde à finir le tour
    cerveau = _cerveau(client)

    flux = cerveau.repondre("Raconte.")
    await anext(flux)
    await asyncio.wait_for(flux.aclose(), timeout=0.5)  # rend la main tout de suite
    await cerveau.fermer()


async def test_une_question_a_la_fois_la_nouvelle_coupe_l_ancienne():
    client = FauxClientClaude(
        [debut_texte(), delta("Première "), BLOQUE, delta("jamais"), fin()],
        reponse("Seconde."),
    )
    cerveau = _cerveau(client)
    premiere: list = []

    async def lire_la_premiere() -> None:
        async for f in cerveau.repondre("une"):
            premiere.append(f)

    tache = asyncio.create_task(lire_la_premiere())
    while not premiere:
        await asyncio.sleep(0)

    assert await _tout(cerveau, "deux") == ["Seconde."]
    await tache  # finie sans erreur : l'interruption n'est pas un échec
    assert premiere == ["Première "]
    assert client.interruptions == 1


async def test_un_menage_qui_ne_finit_pas_repart_de_zero(monkeypatch):
    monkeypatch.setattr(cerveau_claude, "DELAI_MENAGE_S", 0.05)
    bloque = FauxClientClaude([debut_texte(), delta("Long "), BLOQUE])
    bloque.interruption_sans_effet = True
    neuf = FauxClientClaude(reponse("Me revoilà."))
    cerveau = _cerveau(bloque, neuf)

    flux = cerveau.repondre("Raconte.")
    await anext(flux)
    await flux.aclose()

    assert await _tout(cerveau, "Tu es là ?") == [PHRASE_FIL_PERDU + " ", "Me revoilà."]
    assert bloque.deconnexions == 1


# --- l'oubli et le plantage -------------------------------------------------------


async def test_l_oubli_ouvre_une_conversation_neuve_sans_rien_en_dire():
    temps = Temps()
    ancien = FauxClientClaude(reponse("Un."), reponse("Deux."))
    neuf = FauxClientClaude(reponse("Trois."))
    cerveau = _cerveau(ancien, neuf, temps=temps)

    await _tout(cerveau, "un")
    temps.t += 29 * 60
    assert await _tout(cerveau, "deux") == ["Deux."], "moins de trente minutes : on se souvient"
    temps.t += 30 * 60
    assert await _tout(cerveau, "trois") == ["Trois."]
    assert ancien.deconnexions == 1


async def test_apres_un_plantage_en_pleine_reponse_la_suivante_repart_de_zero():
    mort = FauxClientClaude([debut_texte(), delta("Je "), ProcessError("exit code 1")])
    neuf = FauxClientClaude(reponse("Me revoilà."))
    cerveau = _cerveau(mort, neuf)

    with pytest.raises(ErreurCerveau):
        await _tout(cerveau, "un")
    assert await _tout(cerveau, "deux") == [PHRASE_FIL_PERDU + " ", "Me revoilà."]
    assert mort.deconnexions == 1


async def test_un_flux_qui_se_tarit_sans_message_de_fin_est_un_plantage():
    mort = FauxClientClaude([debut_texte(), delta("Je ")])
    neuf = FauxClientClaude(reponse("Me revoilà."))
    cerveau = _cerveau(mort, neuf)

    with pytest.raises(ErreurCerveau, match=ARRET):
        await _tout(cerveau, "un")
    assert (await _tout(cerveau, "deux"))[0] == PHRASE_FIL_PERDU + " "


async def test_un_processus_mort_entre_deux_questions_est_relance():
    mort = FauxClientClaude(reponse("Un."))
    neuf = FauxClientClaude(reponse("Deux."))
    cerveau = _cerveau(mort, neuf)
    await _tout(cerveau, "un")
    mort.echec_question = CLIConnectionError("ProcessTransport is not ready for writing")

    assert await _tout(cerveau, "deux") == [PHRASE_FIL_PERDU + " ", "Deux."]
    assert neuf.questions[0].endswith("\ndeux")


async def test_fermer_deconnecte_le_client():
    client = FauxClientClaude(reponse("Un."))
    cerveau = _cerveau(client)
    await _tout(cerveau, "un")
    await cerveau.fermer()
    assert client.deconnexions == 1


# --- les erreurs ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exception", "message"),
    [
        (CLINotFoundError("Claude Code not found"), ABSENT),
        (CLIConnectionError("Failed to start Claude Code"), INJOIGNABLE),
    ],
)
async def test_un_client_qui_ne_demarre_pas_donne_une_erreur_claire(exception, message):
    client = FauxClientClaude()
    client.echec_connexion = exception
    with pytest.raises(ErreurCerveau) as erreur:
        await _tout(_cerveau(client), "q")
    assert str(erreur.value) == message


@pytest.mark.parametrize(
    ("message_sdk", "attendu"),
    [
        (erreur_assistant("authentication_failed"), DECONNECTE),
        (erreur_assistant("rate_limit"), LIMITE),
        (erreur_assistant("server_error"), INJOIGNABLE),
        (erreur_assistant("billing_error", "API Error: facturation"), "API Error: facturation"),
        (limite("rejected"), LIMITE),
        (fin(is_error=True, api_error_status=429), LIMITE),
        (fin(is_error=True, api_error_status=401), DECONNECTE),
        (fin(is_error=True, api_error_status=529), INJOIGNABLE),
        (fin(is_error=True, errors=["boum"]), "boum"),
    ],
)
async def test_les_erreurs_de_claude_sont_traduites(message_sdk, attendu):
    tour = [debut_texte(), message_sdk, fin()]
    with pytest.raises(ErreurCerveau) as erreur:
        await _tout(_cerveau(FauxClientClaude(tour, reponse("Ok."))), "q")
    assert str(erreur.value) == attendu


async def test_un_avertissement_de_limite_n_est_pas_une_erreur():
    tour = [limite("allowed_warning"), debut_texte(), delta("Oui."), fin()]
    assert await _tout(_cerveau(FauxClientClaude(tour)), "q") == ["Oui."]


async def test_apres_une_erreur_la_conversation_continue():
    client = FauxClientClaude(
        [debut_texte(), erreur_assistant("rate_limit"), fin()], reponse("Ok.")
    )
    cerveau = _cerveau(client)
    with pytest.raises(ErreurCerveau):
        await _tout(cerveau, "un")
    assert await _tout(cerveau, "deux") == ["Ok."], "une limite n'est pas un plantage"
    assert client.connexions == 1


# --- la sécurité ---------------------------------------------------------------------


def test_les_options_enferment_claude_dans_son_role(tmp_path):
    options = options_cerveau("claude-sonnet-5", tmp_path)
    assert options.tools == ["WebSearch"]
    assert options.allowed_tools == ["WebSearch"]
    assert options.setting_sources == []
    assert options.mcp_servers == {}
    assert options.strict_mcp_config is True
    assert options.include_partial_messages is True
    assert options.model == "claude-sonnet-5"
    assert options.cwd == tmp_path
    assert options.system_prompt == CONSIGNES
    assert options.env == {"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"}


def test_la_ligne_de_commande_du_cli_porte_ces_limites(tmp_path):
    # Volontairement branché sur l'intérieur du SDK : si une mise à jour change la façon
    # dont les options deviennent des arguments, ce test doit être revu, pas supprimé.
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    options = dataclasses.replace(options_cerveau("claude-sonnet-5", tmp_path), cli_path="claude")
    commande = SubprocessCLITransport(prompt=None, options=options)._build_command()

    def valeur(drapeau: str) -> str:
        return commande[commande.index(drapeau) + 1]

    assert valeur("--tools") == "WebSearch"
    assert valeur("--allowedTools") == "WebSearch"
    assert valeur("--model") == "claude-sonnet-5"
    assert "--setting-sources=" in commande
    assert "--strict-mcp-config" in commande
    assert "--include-partial-messages" in commande
    assert "--mcp-config" not in commande
    assert "WebFetch" not in " ".join(commande)


def test_les_cles_d_api_sont_retirees_mais_pas_le_jeton_d_abonnement():
    environnement = {
        "ANTHROPIC_API_KEY": "sk-secret",
        "ANTHROPIC_BASE_URL": "https://ailleurs",
        "CLAUDE_CODE_OAUTH_TOKEN": "jeton",
        "PATH": "/usr/bin",
    }
    assert purger_cles_api(environnement) == ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]
    assert environnement == {"CLAUDE_CODE_OAUTH_TOKEN": "jeton", "PATH": "/usr/bin"}


# Le ménage d'une réponse abandonnée (une question qui l'attend puis est elle-même
# annulée ; le tampon plein du SDK) : voir `test_cerveau_claude_menage.py`.
