"""Le serveur « atlas » et les connecteurs : le socle d'abord, puis les outils des connecteurs
actifs, reconstruits à chaque bascule ; les consignes ; et les réactions au fil de la
conversation, qu'un connecteur qui plante ne coupe jamais."""

import logging

import pytest
from test_registre import MANIFESTE, deposer

from atlas_core.memoire import Memoire
from atlas_core.missions import Missions
from atlas_core.outils_memoire import OutilsMemoire
from atlas_core.registre import Registre

TEMOIN = """
from atlas_core.connecteurs import Connecteur, Niveau, Outil


class Temoin(Connecteur):
    def __init__(self):
        self.journal = []

    def noter(self, *quoi):
        self.journal.append(quoi)

    def outils(self):
        async def lire(arguments):
            return "lu"

        return [Outil("{outil}", "Lit.", {{}}, Niveau.N1, lire)]

    def fin_du_tour(self, arretee):
        {agir}("fin_du_tour", arretee)

    def nouvelle_phrase(self):
        {agir}("nouvelle_phrase")

    def nouvelle_conversation(self):
        {agir}("nouvelle_conversation")


def plante(*quoi):
    raise RuntimeError("en panne")


def creer(contexte):
    return Temoin()
"""


def temoin(outil: str, plante: bool = False) -> str:
    agir = "plante" if plante else "self.noter"
    return TEMOIN.format(outil=outil, agir=agir)


@pytest.fixture
def perso(tmp_path):
    return tmp_path / "connecteurs"


def outils_de(tmp_path, perso, **options) -> OutilsMemoire:
    registre = Registre(tmp_path / "officiels", perso, environ={})
    return OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"), registre=registre, **options)


def test_les_outils_d_un_connecteur_suivent_son_interrupteur(tmp_path, perso):
    deposer(perso, "agenda", source=temoin("agenda_lire"))
    outils = outils_de(tmp_path, perso)
    socle = list(outils.noms)
    assert not any("agenda" in nom for nom in socle)
    assert outils.basculer("agenda", True) is True
    assert outils.noms == [*socle, "mcp__atlas__agenda_lire"]
    assert outils.basculer("agenda", True) is False  # déjà actif : rien ne change
    assert outils.basculer("agenda", False) is True
    assert outils.noms == socle


def test_un_connecteur_ne_prend_pas_le_nom_d_un_outil_du_socle(tmp_path, perso):
    deposer(perso, "copie", source=temoin("memoire_lire"))
    outils = outils_de(tmp_path, perso)
    assert outils.basculer("copie", True) is False
    [fiche] = outils.registre.fiches
    assert (fiche.etat, fiche.detail) == ("en_erreur", "nom d'outil déjà pris : memoire_lire")


def test_sans_registre_seul_le_socle(tmp_path):
    outils = OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"))
    assert outils.basculer("poste", True) is False
    assert outils.connecteurs == [] and outils.consignes_des_connecteurs == []


def test_les_consignes_des_connecteurs_actifs(tmp_path, perso):
    deposer(perso, "agenda", source=temoin("agenda_lire"))
    muet = MANIFESTE.format(nom="Muet").replace(
        'consignes = "Dis bonjour quand David te le demande."', ""
    )
    deposer(perso, "muet", muet, source=temoin("muet_lire"))
    outils = outils_de(tmp_path, perso)
    outils.basculer("agenda", True)
    outils.basculer("muet", True)
    assert outils.consignes_des_connecteurs == ["Dis bonjour quand David te le demande."]


def test_les_connecteurs_suivent_la_conversation_meme_si_l_un_plante(tmp_path, perso, caplog):
    deposer(perso, "a-panne", source=temoin("panne_lire", plante=True))
    deposer(perso, "temoin", source=temoin("temoin_lire"))
    fins: list[str] = []
    missions = Missions(sur_fin=fins.append)
    outils = outils_de(tmp_path, perso, missions=missions)
    outils.basculer("a-panne", True)
    outils.basculer("temoin", True)
    with caplog.at_level(logging.ERROR):
        outils.nouvelle_phrase()
        outils.fin_du_tour(arretee=True)
        outils.nouvelle_conversation()
    temoin_charge = next(c for c in outils.connecteurs if c.id == "temoin").connecteur
    assert temoin_charge.journal == [
        ("nouvelle_phrase",),
        ("fin_du_tour", True),
        ("nouvelle_conversation",),
    ]
    assert caplog.text.count("le connecteur a-panne a échoué") == 3


def test_un_connecteur_qui_appelle_sys_exit_n_arrete_pas_le_core(tmp_path, perso, caplog):
    source = temoin("sortie_lire", plante=True).replace("RuntimeError(", "SystemExit(")
    deposer(perso, "a-sortie", source=source)
    deposer(perso, "temoin", source=temoin("temoin_lire"))
    outils = outils_de(tmp_path, perso)
    outils.basculer("a-sortie", True)
    outils.basculer("temoin", True)
    with caplog.at_level(logging.ERROR):
        outils.nouvelle_phrase()
        outils.fin_du_tour(arretee=False)
    temoin_charge = next(c for c in outils.connecteurs if c.id == "temoin").connecteur
    assert temoin_charge.journal == [("nouvelle_phrase",), ("fin_du_tour", False)]
    assert caplog.text.count("le connecteur a-sortie a échoué") == 2


def test_la_conversation_neuve_dit_aux_pages_que_les_bascules_ont_pris_effet(tmp_path, perso):
    deposer(perso, "agenda", source=temoin("agenda_lire"))
    annonces: list[str] = []
    outils = outils_de(tmp_path, perso, sur_connecteurs=lambda: annonces.append("liste"))
    outils.conversation_commencee()
    assert annonces == [], "sans bascule en attente, rien à dire"
    outils.basculer("agenda", True)
    assert [f.en_attente for f in outils.registre.fiches] == [True]
    outils.nouvelle_conversation()  # l'ancienne se clôt : la bascule attend encore la question
    assert annonces == [] and [f.en_attente for f in outils.registre.fiches] == [True]
    outils.conversation_commencee()  # la première question de la neuve est partie
    assert annonces == ["liste"]
    assert [f.en_attente for f in outils.registre.fiches] == [False]


def test_les_outils_d_un_connecteur_retire_du_disque_partent_a_la_conversation_neuve(
    tmp_path, perso
):
    import shutil

    dossier = deposer(perso, "agenda", source=temoin("agenda_lire"))
    outils = outils_de(tmp_path, perso)
    outils.basculer("agenda", True)
    shutil.rmtree(dossier)
    outils.registre.decouvrir()  # une page ouvre ses Paramètres
    assert "mcp__atlas__agenda_lire" in outils.noms  # la conversation en cours garde les siens
    outils.nouvelle_conversation()
    assert "mcp__atlas__agenda_lire" not in outils.noms and outils.connecteurs == []
