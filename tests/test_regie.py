from atlas_core.diffuseur import Diffuseur
from atlas_core.protocole_web import Muet
from atlas_core.regie import Regie


class SessionEspionne:
    def __init__(self) -> None:
        self.saisies: list[str] = []
        self.taire_appels = 0

    async def sur_saisie(self, texte: str) -> None:
        self.saisies.append(texte)

    async def taire(self) -> None:
        self.taire_appels += 1


class DiffuseurEspion(Diffuseur):
    def __init__(self) -> None:
        super().__init__()
        self.publies: list = []

    def publier(self, msg) -> None:
        self.publies.append(msg)
        super().publier(msg)


def _regie():
    creees: list[SessionEspionne] = []

    def fabrique() -> SessionEspionne:
        creees.append(SessionEspionne())
        return creees[-1]

    return Regie(DiffuseurEspion(), fabrique), creees


def test_la_voix_est_active_par_defaut():
    regie, _ = _regie()
    assert regie.muet is False and regie.voix_active() is True


async def test_une_question_tapee_va_au_client_audio_connecte():
    regie, creees = _regie()
    audio = SessionEspionne()
    regie.rattacher(audio)
    await regie.saisie("quelle heure est-il")
    assert audio.saisies == ["quelle heure est-il"] and creees == []


async def test_sans_client_audio_une_seule_session_ecrite_est_creee():
    regie, creees = _regie()
    await regie.saisie("un")
    await regie.saisie("deux")
    assert len(creees) == 1 and creees[0].saisies == ["un", "deux"]


async def test_detacher_le_client_audio_renvoie_vers_la_session_ecrite():
    regie, creees = _regie()
    audio = SessionEspionne()
    regie.rattacher(audio)
    regie.detacher(SessionEspionne())  # une autre session : sans effet
    await regie.saisie("un")
    regie.detacher(audio)
    await regie.saisie("deux")
    assert audio.saisies == ["un"] and creees[0].saisies == ["deux"]


async def test_le_muet_est_publie_et_fait_taire_le_client_audio():
    regie, _ = _regie()
    audio = SessionEspionne()
    regie.rattacher(audio)
    await regie.basculer_muet(True)
    assert regie.muet is True and regie.voix_active() is False
    assert regie.diffuseur.publies == [Muet(actif=True)]
    assert audio.taire_appels == 1
    await regie.basculer_muet(False)
    assert regie.voix_active() is True and audio.taire_appels == 1
    assert regie.diffuseur.publies[-1] == Muet(actif=False)


async def test_le_muet_sans_client_audio_ne_plante_pas():
    regie, _ = _regie()
    await regie.basculer_muet(True)
    assert regie.muet is True
