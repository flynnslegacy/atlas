import pytest

from helios_core.etat import MachineEtat, TransitionInterdite


def test_l_etat_de_depart_est_le_repos():
    assert MachineEtat().valeur == "repos"


@pytest.mark.parametrize(
    "depart,arrivee",
    [
        ("repos", "ecoute"),
        ("ecoute", "reflexion"),
        ("reflexion", "parole"),
        ("parole", "repos"),
        ("parole", "ecoute"),
        ("ecoute", "repos"),
    ],
)
def test_les_transitions_permises_passent(depart, arrivee):
    m = MachineEtat(depart)
    m.aller_vers(arrivee)
    assert m.valeur == arrivee


@pytest.mark.parametrize(
    "depart,arrivee",
    [("repos", "parole"), ("repos", "reflexion"), ("ecoute", "parole"), ("reflexion", "ecoute")],
)
def test_les_transitions_interdites_levent(depart, arrivee):
    m = MachineEtat(depart)
    with pytest.raises(TransitionInterdite):
        m.aller_vers(arrivee)


def test_peut_aller_vers_ne_leve_pas():
    m = MachineEtat()
    assert m.peut_aller_vers("ecoute") is True
    assert m.peut_aller_vers("parole") is False
    assert m.valeur == "repos"
