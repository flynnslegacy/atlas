"""Garde-fous de la page web : origine des connexions, clé d'accès, politique de sécurité."""

from __future__ import annotations

import hmac
import re
from urllib.parse import urlsplit

# Un hôte « normal » (nom ou IPv4, IPv6 entre crochets, port facultatif) : lui seul entre
# dans l'en-tête de politique de sécurité, pour qu'un en-tête Host fantaisiste n'y
# injecte rien.
_HOTE_SUR = re.compile(r"(?:[A-Za-z0-9.\-]+|\[[0-9A-Fa-f:.]+\])(?::\d{1,5})?")


def origine_autorisee(origine: str | None, hote: str | None) -> bool:
    """La connexion vient-elle de la page servie par ce même Core ?"""
    if not origine or not hote:
        return False
    try:
        netloc = urlsplit(origine).netloc
    except ValueError:
        return False
    return bool(netloc) and netloc.lower() == hote.lower()


def cle_valide(proposee: str, attendue: str) -> bool:
    """Comparaison en temps constant ; une clé attendue vide ne valide jamais rien."""
    if not attendue:
        return False
    return hmac.compare_digest(proposee.encode(), attendue.encode())


def politique_securite(hote: str) -> str:
    connexions = "'self'"
    if _HOTE_SUR.fullmatch(hote or ""):
        connexions += f" ws://{hote} wss://{hote}"
    return (
        "default-src 'self'; "
        f"connect-src {connexions}; "
        "img-src 'self' data:; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
