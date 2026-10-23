"""The fictional league: clubs, squads and the fixture list the app offers.

A fixture is `{id, seed, home, away}`: the seed makes the match (events never depend on the clubs), the clubs only name it.
Seed 7 is the demo match Northport v Valemont, with its pre-generated caches.
"""
from __future__ import annotations

CLUBS = {
    "northport": {"name": "Northport", "color": "red",
                  "players": ["Usta", "Aksoy", "Demir", "Toprak", "Kurt", "Kaya", "Polat", "Erdem", "Şahin", "Arda", "Yıldız"]},
    "valemont": {"name": "Valemont", "color": "blue",
                 "players": ["Novak", "Moreau", "Haddad", "Lindqvist", "Costa", "Silva", "Mensah", "Ito", "Baptiste", "Okafor", "Rossi"]},
}
FIXTURES = [
    {"id": "northport-valemont", "seed": 7, "home": "northport", "away": "valemont"},
]
DEFAULT_MATCH = "northport-valemont"


def fixture(match_id: str) -> dict:
    """The fixture with this id; unknown -> the default match."""
    return next((f for f in FIXTURES if f["id"] == match_id), next(f for f in FIXTURES if f["id"] == DEFAULT_MATCH))
