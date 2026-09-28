"""Le registre des connecteurs (spec des connecteurs, §5) : ce qui est déposé, ce qui est
activé, ce qui est chargé.

Deux répertoires : les connecteurs officiels, dans le dépôt, et ceux de David et de la
communauté (`~/.atlas/connecteurs/`). Le registre les relit à la demande en ne lisant que
les manifestes : aucun code n'y tourne. Le code d'un connecteur ne se charge qu'à son
activation (par David dans la page, ou au démarrage s'il l'avait activé), et un connecteur
qui plante passe « en erreur » sans jamais faire tomber Atlas. Les interrupteurs sont rangés
dans un fichier voisin du répertoire (`~/.atlas/connecteurs.json`), lisible par David seul,
chacun lié à l'origine du connecteur (`communaute:meteo`) : un dossier retiré emporte son
interrupteur, et un autre code déposé sous le même nom repart coupé.

`python -m atlas_core.registre installer` (dans `make install`) installe les dépendances de
tous les connecteurs trouvés, bornées par le verrou d'Atlas (`uv.lock`).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import types
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import jsonschema  # installé avec le SDK de Claude, qui valide ainsi les arguments des outils

from .connecteurs import (
    ID_MAX,
    MOTIF_ID,
    MOTIF_OUTIL,
    Connecteur,
    Contexte,
    Manifeste,
    Niveau,
    Outil,
    distribution,
    lire_manifeste,
)

if TYPE_CHECKING:
    from .missions import Missions
    from .poste import Poste

_journal = logging.getLogger(__name__)

DEPOT = Path(__file__).resolve().parents[2]
OFFICIELS = DEPOT / "connecteurs"
RACINE_DES_MODULES = "atlas_connecteurs"
DETAIL_MAX = 300

Etat = Literal["actif", "coupe", "a_configurer", "a_installer", "en_erreur"]
Origine = Literal["atlas", "communaute"]


class ConnecteurInvalide(ValueError):
    """Le registre refuse ce que rend un connecteur (ses outils) : la raison se lit telle
    quelle dans la page."""


@dataclass(frozen=True)
class Fiche:
    """Un connecteur tel que la page le montre."""

    id: str
    origine: Origine
    dossier: Path
    manifeste: Manifeste | None
    etat: Etat
    detail: str = ""
    en_attente: bool = False  # basculé : prend effet à la question suivante

    @property
    def activable(self) -> bool:
        return self.etat in ("actif", "coupe")


@dataclass(frozen=True)
class ConnecteurActif:
    """Un connecteur chargé : lui, ses outils (vérifiés au chargement) et les consignes de
    son manifeste."""

    id: str
    connecteur: Connecteur
    outils: tuple[Outil, ...]
    consignes: str
    dossier: Path


@dataclass
class _Echec:
    raison: str
    signature: int  # l'état du dossier au moment de l'échec : s'il change, on réessaie


@dataclass
class _Charges:
    actifs: dict[str, ConnecteurActif] = field(default_factory=dict)
    echecs: dict[str, _Echec] = field(default_factory=dict)


def fichier_des_interrupteurs(dossier: Path) -> Path:
    """Voisin du répertoire : `~/.atlas/connecteurs` → `~/.atlas/connecteurs.json`."""
    return dossier.with_name(dossier.name + ".json")


def _installe(nom: str) -> bool:
    try:
        importlib.metadata.distribution(nom)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


class Registre:
    def __init__(
        self,
        officiels: Path,
        perso: Path,
        *,
        environ: Mapping[str, str] | None = None,
        poste: Poste | None = None,
        missions: Missions | None = None,
        installe: Callable[[str], bool] = _installe,
    ) -> None:
        self._officiels, self._perso = officiels, perso
        self._interrupteurs = fichier_des_interrupteurs(perso)
        self._environ = os.environ if environ is None else environ
        self._poste, self._missions = poste, missions
        self._installe = installe
        self._reserves: set[str] = set()
        self._charges = _Charges()
        self._en_attente: set[str] = set()
        self._fiches: list[Fiche] = []

    def reserver(self, noms: Iterable[str]) -> None:
        """Les noms des outils du socle, qu'aucun connecteur ne peut prendre."""
        self._reserves |= set(noms)

    # --- ce qui est déposé ----------------------------------------------------------

    def decouvrir(self) -> list[Fiche]:
        """Relit les deux répertoires, manifestes seuls ; les officiels d'abord."""
        fiches: list[Fiche] = []
        officiels: set[str] = set()
        lisibles: set[str] = set()
        for origine, racine in (("atlas", self._officiels), ("communaute", self._perso)):
            dossiers = _sous_dossiers(racine)
            if dossiers is None:
                continue
            lisibles.add(origine)
            for dossier in dossiers:
                fiches.append(self._fiche(origine, dossier, officiels))
                if origine == "atlas":
                    officiels.add(dossier.name)
        # Un connecteur chargé dont le dossier a disparu (ou n'est plus valable) se décharge :
        # ses outils quittent Claude à la conversation neuve.
        restent = {f.id for f in fiches if f.etat == "actif"}
        for id_ in [i for i in self._charges.actifs if i not in restent]:
            del self._charges.actifs[id_]
            _oublier_le_module(id_)
            _journal.info("connecteur %s retiré : déchargé", id_)
        # Son interrupteur part avec lui ; un répertoire momentanément illisible ne dit
        # rien de ses dossiers, et garde les siens.
        actives = self._lire_interrupteurs()
        presentes = {_cle(f.origine, f.id) for f in fiches}
        gardees = {c for c in actives if c in presentes or c.split(":")[0] not in lisibles}
        if gardees != actives:
            self._ecrire_interrupteurs(gardees)
        self._fiches = fiches
        return list(fiches)

    def _fiche(self, origine: Origine, dossier: Path, officiels: set[str]) -> Fiche:
        id_ = dossier.name

        def fiche(etat: Etat, detail: str = "", manifeste: Manifeste | None = None) -> Fiche:
            attente = id_ in self._en_attente
            return Fiche(id_, origine, dossier, manifeste, etat, detail[:DETAIL_MAX], attente)

        if len(id_) > ID_MAX or not re.fullmatch(MOTIF_ID, id_):
            return fiche("en_erreur", "nom de dossier invalide : minuscules, chiffres et tirets")
        if origine == "communaute" and id_ in officiels:
            return fiche("en_erreur", "déjà fourni par Atlas")
        try:
            manifeste = lire_manifeste(dossier)
        except ValueError as e:
            return fiche("en_erreur", str(e))
        charge = self._charges.actifs.get(id_)
        if charge is not None and charge.dossier == dossier:
            return fiche("actif", manifeste=manifeste)
        echec = self._charges.echecs.get(id_)
        if echec is not None and echec.signature == _signature(dossier):
            return fiche("en_erreur", echec.raison, manifeste)
        manquants = [
            r.variable for r in manifeste.reglages if not self._environ.get(r.variable, "").strip()
        ]
        if manquants:
            detail = f"il manque {', '.join(manquants)} dans le .env du Core"
            return fiche("a_configurer", detail, manifeste)
        absents = [
            distribution(d) for d in manifeste.dependances if not self._installe(distribution(d))
        ]
        if absents:
            return fiche(
                "a_installer", f"lance make install (il manque {', '.join(absents)})", manifeste
            )
        return fiche("coupe", manifeste=manifeste)

    # --- ce qui est activé ------------------------------------------------------------

    def demarrer(self) -> None:
        """Au démarrage du Core : charge les connecteurs que David avait activés, s'ils sont
        activables ; un échec n'empêche pas les autres, et coupe le sien : la page le montre
        en erreur, et un code changé ne s'activera pas sans que David le voie."""
        fiches = self.decouvrir()
        actives = self._lire_interrupteurs()
        echoues = {
            _cle(f.origine, f.id)
            for f in fiches
            if _cle(f.origine, f.id) in actives and f.etat == "coupe" and not self._charger(f)
        }
        if echoues:
            self._ecrire_interrupteurs(actives - echoues)
        self.decouvrir()

    def basculer(self, id_: str, actif: bool) -> bool:
        """Active ou coupe un connecteur découvert ; rend vrai si les connecteurs actifs ont
        changé. Un identifiant inconnu, ou un connecteur qui n'est pas activable, ne change
        rien : aucun chemin n'est jamais tiré du texte reçu."""
        fiche = next((f for f in self.decouvrir() if f.id == id_), None)
        if fiche is None:
            return False
        actives, cle = self._lire_interrupteurs(), _cle(fiche.origine, id_)
        change = False
        if actif and fiche.etat == "coupe":
            change = self._charger(fiche)
            if change:
                self._ecrire_interrupteurs(actives | {cle})
        elif not actif:
            if id_ in self._charges.actifs:
                self._charges.actifs.pop(id_)
                _oublier_le_module(id_)
                change = True
            if cle in actives:
                self._ecrire_interrupteurs(actives - {cle})
        if change:
            self._en_attente.add(id_)
        self.decouvrir()
        return change

    def appliquer(self) -> bool:
        """La conversation neuve a commencé : les bascules ont pris effet. Rend vrai s'il y
        en avait en attente."""
        if not self._en_attente:
            return False
        self._en_attente.clear()
        self.decouvrir()
        return True

    @property
    def fiches(self) -> list[Fiche]:
        return list(self._fiches)

    def actifs(self) -> list[ConnecteurActif]:
        """Les connecteurs chargés, dans l'ordre de la page."""
        return [self._charges.actifs[f.id] for f in self._fiches if f.id in self._charges.actifs]

    def secrets(self) -> list[str]:
        """Les valeurs des réglages secrets de tous les connecteurs trouvés : la mémoire
        refuse de les écrire."""
        return [
            valeur
            for f in self._fiches
            if f.manifeste is not None
            for r in f.manifeste.reglages
            if r.secret and (valeur := self._environ.get(r.variable, "").strip())
        ]

    # --- le chargement --------------------------------------------------------------

    def _charger(self, fiche: Fiche) -> bool:
        manifeste = fiche.manifeste
        assert manifeste is not None
        try:
            module = _importer(fiche.id, fiche.dossier)
            connecteur = module.creer(self._contexte(manifeste))
            outils = connecteur.outils()
            self._verifier(outils)
        except (Exception, SystemExit) as e:  # noqa: BLE001 — jamais une panne d'Atlas
            _journal.exception("le connecteur %s ne se charge pas", fiche.id)
            _oublier_le_module(fiche.id)
            if isinstance(e, ConnecteurInvalide):
                raison = str(e)
            else:
                raison = f"{type(e).__name__} : {e}" if str(e) else type(e).__name__
            self._charges.echecs[fiche.id] = _Echec(raison, _signature(fiche.dossier))
            return False
        self._charges.echecs.pop(fiche.id, None)
        actif = ConnecteurActif(
            fiche.id, connecteur, tuple(outils), manifeste.consignes, fiche.dossier
        )
        self._charges.actifs[fiche.id] = actif
        _journal.info("connecteur %s chargé", fiche.id)
        return True

    def _contexte(self, manifeste: Manifeste) -> Contexte:
        reglages = {
            r.variable: self._environ.get(r.variable, "").strip() for r in manifeste.reglages
        }
        if "poste" in manifeste.services:
            return Contexte(reglages, poste=self._poste, missions=self._missions)
        return Contexte(reglages)

    def _verifier(self, outils: object) -> None:
        pris = self._reserves | {o.nom for a in self._charges.actifs.values() for o in a.outils}
        if not isinstance(outils, list) or not all(isinstance(o, Outil) for o in outils):
            raise ConnecteurInvalide("outils() doit rendre une liste d'Outil")
        for outil in outils:
            if not re.fullmatch(MOTIF_OUTIL, outil.nom):
                raise ConnecteurInvalide(f"nom d'outil invalide : {outil.nom}")
            if not isinstance(outil.niveau, Niveau):
                raise ConnecteurInvalide(f"niveau invalide pour {outil.nom}")
            # Ce que l'API de Claude refuserait ferait échouer chaque conversation.
            if not isinstance(outil.description, str) or not outil.description.strip():
                raise ConnecteurInvalide(f"description invalide pour {outil.nom}")
            if not _parametres_valables(outil.parametres):
                raise ConnecteurInvalide(f"paramètres invalides pour {outil.nom}")
            if not callable(outil.gestionnaire):
                raise ConnecteurInvalide(f"gestionnaire invalide pour {outil.nom}")
            if outil.nom in pris:
                raise ConnecteurInvalide(f"nom d'outil déjà pris : {outil.nom}")
            pris.add(outil.nom)

    # --- les interrupteurs ----------------------------------------------------------

    def _lire_interrupteurs(self) -> set[str]:
        try:
            donnees = json.loads(self._interrupteurs.read_text(encoding="utf-8"))
            return {str(i) for i in donnees["actifs"]}
        except FileNotFoundError:
            return set()
        except (OSError, ValueError, KeyError, TypeError) as e:
            _journal.warning("interrupteurs des connecteurs illisibles (%s) : tous coupés", e)
            return set()

    def _ecrire_interrupteurs(self, actives: set[str]) -> None:
        temporaire = self._interrupteurs.with_name(self._interrupteurs.name + ".tmp")
        try:
            self._interrupteurs.parent.mkdir(parents=True, exist_ok=True)
            descripteur = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
                json.dump({"actifs": sorted(actives)}, fichier, ensure_ascii=False, indent=2)
            os.chmod(temporaire, 0o600)
            os.replace(temporaire, self._interrupteurs)
        except OSError as e:
            _journal.warning("interrupteurs des connecteurs non enregistrés : %s", e)


_TYPES_SIMPLES = (str, int, float, bool, list, dict)


def _parametres_valables(parametres: object) -> bool:
    """Des types simples par argument (`{"jour": str}`), ou un schéma JSON d'objet valable."""
    if not isinstance(parametres, dict) or not all(isinstance(c, str) for c in parametres):
        return False
    if parametres.get("type") == "object" and isinstance(parametres.get("properties"), dict):
        try:
            jsonschema.validators.validator_for(parametres).check_schema(parametres)
        except jsonschema.SchemaError:
            return False
        return True
    return all(valeur in _TYPES_SIMPLES for valeur in parametres.values())


def _cle(origine: str, id_: str) -> str:
    return f"{origine}:{id_}"


def _sous_dossiers(racine: Path) -> list[Path] | None:
    """Les dossiers de connecteurs d'un répertoire ; aucun s'il n'existe pas, None s'il
    est illisible."""
    try:
        return sorted(
            p for p in racine.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))
        )
    except FileNotFoundError:
        return []
    except OSError as e:
        _journal.warning("répertoire des connecteurs illisible : %s (%s)", racine, e)
        return None


def _signature(dossier: Path) -> int:
    try:
        return max((p.stat().st_mtime_ns for p in dossier.rglob("*") if p.is_file()), default=0)
    except OSError:
        return 0


def _nom_du_module(id_: str) -> str:
    return f"{RACINE_DES_MODULES}.{id_.replace('-', '_')}"


def _oublier_le_module(id_: str) -> None:
    nom = _nom_du_module(id_)
    for charge in [m for m in sys.modules if m == nom or m.startswith(nom + ".")]:
        del sys.modules[charge]


def _importer(id_: str, dossier: Path) -> types.ModuleType:
    """Charge `connecteur.py` du dossier comme module d'un paquet à son nom, frais : un
    connecteur retouché puis réactivé relit son code."""
    _oublier_le_module(id_)
    if RACINE_DES_MODULES not in sys.modules:
        racine = types.ModuleType(RACINE_DES_MODULES)
        racine.__path__ = []
        sys.modules[RACINE_DES_MODULES] = racine
    nom = _nom_du_module(id_)
    paquet = types.ModuleType(nom)
    paquet.__path__ = [str(dossier)]
    sys.modules[nom] = paquet
    importlib.invalidate_caches()
    return importlib.import_module(f"{nom}.connecteur")


def installer(
    registre: Registre, lancer: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> int:
    """Installe, dans l'environnement d'Atlas, les dépendances de tous les connecteurs
    trouvés, coupés compris, sans jamais changer une version dont Atlas dépend : le verrou
    les borne. Les officiels s'installent ensemble, puis chaque connecteur de la communauté
    à part ; un échec de ceux-là le laisse « à installer » sans faire échouer `make install`.
    Rend le code de retour."""
    groupes: list[tuple[str, list[str]]] = []
    officielles: set[str] = set()
    for fiche in registre.decouvrir():
        if fiche.manifeste is None or not fiche.manifeste.dependances:
            continue
        if fiche.origine == "atlas":
            officielles |= set(fiche.manifeste.dependances)
        else:
            groupes.append((fiche.id, list(fiche.manifeste.dependances)))
    if officielles:
        groupes.insert(0, ("", sorted(officielles)))
    if not groupes:
        return 0
    with tempfile.TemporaryDirectory() as dossier:
        verrou = str(Path(dossier) / "verrou.txt")
        exporter = ["uv", "export", "--project", str(DEPOT), "--frozen", "--no-hashes"]
        exporter += ["--no-emit-project", "--all-extras", "--quiet", "-o", verrou]
        code = lancer(exporter, check=False).returncode
        if code:
            print("Le verrou d'Atlas ne se lit pas : aucune dépendance de connecteur installée.")
            return code
        for id_, dependances in groupes:
            qui = f"du connecteur {id_}" if id_ else "des connecteurs d'Atlas"
            print(f"Dépendances {qui} :", ", ".join(dependances))
            installe = ["uv", "pip", "install", "-c", verrou, *dependances]
            if (rate := lancer(installe, check=False).returncode) and not id_:
                code = rate
            elif rate:
                print(f"Le connecteur {id_} reste « à installer » : ses dépendances ne vont pas")
                print("avec celles d'Atlas, ou ne se trouvent pas.")
    return code


if __name__ == "__main__":
    from .config import Config

    if sys.argv[1:] != ["installer"]:
        sys.exit("usage : python -m atlas_core.registre installer")
    sys.exit(installer(Registre(OFFICIELS, Config.depuis_environnement().connecteurs_dossier)))
