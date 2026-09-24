from atlas_core.config import Config


def test_la_cle_web_vient_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_WEB_CLE", "  cle-secrete  ")
    assert Config.depuis_environnement().web_cle == "cle-secrete"


def test_sans_cle_web_la_valeur_est_vide(monkeypatch):
    monkeypatch.delenv("ATLAS_WEB_CLE", raising=False)
    assert Config.depuis_environnement().web_cle == ""
