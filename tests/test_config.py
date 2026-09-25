from pathlib import Path

import pytest

from atlas_core.config import MEMOIRE_PAR_DEFAUT, Config


def test_la_cle_web_vient_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_WEB_CLE", "  cle-secrete  ")
    assert Config.depuis_environnement().web_cle == "cle-secrete"


def test_sans_cle_web_la_valeur_est_vide(monkeypatch):
    monkeypatch.delenv("ATLAS_WEB_CLE", raising=False)
    assert Config.depuis_environnement().web_cle == ""


def test_les_reglages_du_cerveau_ont_des_valeurs_par_defaut(monkeypatch):
    for nom in ("ATLAS_CERVEAU", "ATLAS_CERVEAU_MODELE", "ATLAS_CERVEAU_OUBLI_MIN"):
        monkeypatch.delenv(nom, raising=False)
    config = Config.depuis_environnement()
    assert config.cerveau == "claude"
    assert config.cerveau_modele == "claude-sonnet-5"
    assert config.cerveau_oubli_min == 30.0


def test_les_reglages_du_cerveau_viennent_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_CERVEAU", " Bouchon ")
    monkeypatch.setenv("ATLAS_CERVEAU_MODELE", "claude-opus-5-5")
    monkeypatch.setenv("ATLAS_CERVEAU_OUBLI_MIN", "12.5")
    config = Config.depuis_environnement()
    assert config.cerveau == "bouchon"
    assert config.cerveau_modele == "claude-opus-5-5"
    assert config.cerveau_oubli_min == 12.5


def test_un_modele_vide_reprend_le_modele_par_defaut(monkeypatch):
    monkeypatch.setenv("ATLAS_CERVEAU_MODELE", "  ")
    assert Config.depuis_environnement().cerveau_modele == "claude-sonnet-5"


def test_un_cerveau_inconnu_est_refuse(monkeypatch):
    monkeypatch.setenv("ATLAS_CERVEAU", "gpt")
    with pytest.raises(ValueError, match="ATLAS_CERVEAU"):
        Config.depuis_environnement()


@pytest.mark.parametrize("brute", ["pas-un-nombre", "0", "-5", "nan", "inf"])
def test_un_delai_d_oubli_invalide_est_refuse(monkeypatch, brute):
    monkeypatch.setenv("ATLAS_CERVEAU_OUBLI_MIN", brute)
    with pytest.raises(ValueError, match="ATLAS_CERVEAU_OUBLI_MIN"):
        Config.depuis_environnement()


def test_la_cle_audio_vient_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_AUDIO_CLE", "  cle-audio  ")
    assert Config.depuis_environnement().audio_cle == "cle-audio"


def test_sans_cle_audio_la_valeur_est_vide(monkeypatch):
    monkeypatch.delenv("ATLAS_AUDIO_CLE", raising=False)
    assert Config.depuis_environnement().audio_cle == ""


def test_les_reglages_de_la_voix_des_pages_ont_les_valeurs_du_spike(monkeypatch):
    monkeypatch.delenv("ATLAS_VOIX_MARGE_S", raising=False)
    monkeypatch.delenv("ATLAS_VOIX_BARGEIN_DBFS", raising=False)
    config = Config.depuis_environnement()
    assert config.voix_marge_s == 0.2 and config.voix_bargein_dbfs == -40.0


def test_les_reglages_de_la_voix_des_pages_viennent_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_VOIX_MARGE_S", "0.35")
    monkeypatch.setenv("ATLAS_VOIX_BARGEIN_DBFS", "-45.5")
    config = Config.depuis_environnement()
    assert config.voix_marge_s == 0.35 and config.voix_bargein_dbfs == -45.5


@pytest.mark.parametrize(
    ("nom", "brute"),
    [
        ("ATLAS_VOIX_MARGE_S", "vite"),
        ("ATLAS_VOIX_MARGE_S", "-0.1"),
        ("ATLAS_VOIX_MARGE_S", "3"),
        ("ATLAS_VOIX_MARGE_S", "nan"),
        ("ATLAS_VOIX_BARGEIN_DBFS", "fort"),
        ("ATLAS_VOIX_BARGEIN_DBFS", "5"),
        ("ATLAS_VOIX_BARGEIN_DBFS", "-200"),
        ("ATLAS_VOIX_BARGEIN_DBFS", "-inf"),
    ],
)
def test_un_reglage_de_la_voix_des_pages_invalide_est_refuse(monkeypatch, nom, brute):
    monkeypatch.setenv(nom, brute)
    with pytest.raises(ValueError, match=nom):
        Config.depuis_environnement()


def test_la_memoire_vit_par_defaut_dans_le_dossier_d_atlas(monkeypatch):
    monkeypatch.delenv("ATLAS_MEMOIRE_DOSSIER", raising=False)
    assert Config.depuis_environnement().memoire_dossier == MEMOIRE_PAR_DEFAUT
    assert MEMOIRE_PAR_DEFAUT == Path.home() / ".atlas" / "memoire"
    monkeypatch.setenv("ATLAS_MEMOIRE_DOSSIER", "  ")
    assert Config.depuis_environnement().memoire_dossier == MEMOIRE_PAR_DEFAUT


def test_le_dossier_de_la_memoire_se_regle_et_accepte_le_tilde(monkeypatch):
    monkeypatch.setenv("ATLAS_MEMOIRE_DOSSIER", "~/atlas-memoire")
    assert Config.depuis_environnement().memoire_dossier == Path.home() / "atlas-memoire"
