"""Le guide des connecteurs (`connecteurs/LISEZMOI.md`) tient ses promesses : son connecteur
minimal, copié tel quel, se charge et répond, et son exemple de test passe."""

import importlib.util
import re
from pathlib import Path

from atlas_core.registre import OFFICIELS, Registre

GUIDE = OFFICIELS / "LISEZMOI.md"


def bloc(fichier: str) -> str:
    """Le bloc de code qui suit la ligne « `fichier` : » dans le guide."""
    texte = GUIDE.read_text(encoding="utf-8")
    trouve = re.search(rf"^`{re.escape(fichier)}` :\n\n```[a-z]+\n(.*?)\n```$", texte, re.M | re.S)
    assert trouve, f"le guide ne montre pas {fichier}"
    return trouve.group(1) + "\n"


def copier_le_guide(dossier: Path) -> None:
    (dossier / "bonjour").mkdir(parents=True)
    for fichier in ("bonjour/connecteur.toml", "bonjour/connecteur.py", "test_bonjour.py"):
        (dossier / fichier).write_text(bloc(fichier), encoding="utf-8")


async def test_le_connecteur_minimal_du_guide_se_charge_et_repond(tmp_path):
    copier_le_guide(tmp_path / "guide")
    assert len(bloc("bonjour/connecteur.py").splitlines()) <= 25, "une vingtaine de lignes"
    registre = Registre(
        tmp_path / "guide", tmp_path / "rien", environ={"ATLAS_BONJOUR_NOM": "David"}
    )
    assert registre.basculer("bonjour", True), registre.fiches
    [actif] = registre.actifs()
    assert actif.consignes == "Quand David te demande de le saluer, appelle bonjour_dire."
    assert await actif.outils[0].gestionnaire({}) == "Bonjour David !"
    sans_nom = Registre(tmp_path / "guide", tmp_path / "rien2", environ={})
    [fiche] = sans_nom.decouvrir()
    assert fiche.etat == "a_configurer"


async def test_l_exemple_de_test_du_guide_passe(tmp_path):
    copier_le_guide(tmp_path / "guide")
    spec = importlib.util.spec_from_file_location(
        "test_bonjour", tmp_path / "guide" / "test_bonjour.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    await module.test_bonjour_salue_par_le_nom_regle(tmp_path / "temporaire")
