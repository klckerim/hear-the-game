"""The fictional league: clubs, squads and the fixture list the app offers.

A fixture is `{id, seed, home, away}`: the seed makes the match (events never depend on the clubs), the clubs only name it.
Seed 7 is the demo match Northport v Valemont, with its pre-generated caches.
"""
from __future__ import annotations

# Six fictional clubs (owner-approved 2026-10-23; a web search found no professional club by these names, Zekteris is the owner's
# choice). Same spelling in EN and TR. No green kit (the pitch is green). Squads are in htg.generate.ROLES order (GK, FB, CB, CB, FB,
# CM, CM, CM, W, ST, W); surnames are unique across the league (callout clips are keyed by name).
CLUBS = {
    "northport": {"name": "Northport", "color": "red",
                  "players": ["Usta", "Aksoy", "Demir", "Toprak", "Kurt", "Kaya", "Polat", "Erdem", "Şahin", "Arda", "Yıldız"]},
    "valemont": {"name": "Valemont", "color": "blue",
                 "players": ["Novak", "Moreau", "Haddad", "Lindqvist", "Costa", "Silva", "Mensah", "Ito", "Baptiste", "Okafor", "Rossi"]},
    "kingsmoor": {"name": "Kingsmoor", "color": "yellow",
                  "players": ["Whitlock", "Ayodele", "Marchetti", "Coyle", "Henriksen", "Dobrev", "Okonjo", "Ferrand", "Pascoe", "Lindgren",
                              "Akande"]},
    "lornbridge": {"name": "Lornbridge", "color": "orange",
                   "players": ["Garrow", "Tanaka", "Rusu", "Kessler", "Doherty", "Nwosu", "Albrecht", "Quinlan", "Moretti", "Saidi",
                               "Holm"]},
    "zekteris": {"name": "Zekteris", "color": "white",
                 "players": ["Arslan", "Karadağ", "Petrov", "Duval", "Ekström", "Bakari", "Yılmazer", "Castellano", "Oyelaran", "Nakamura",
                             "Rinaldi"]},
    "thornfield": {"name": "Thornfield", "color": "purple",
                   "players": ["Ashby", "Kovač", "Delacroix", "Mwangi", "Lund", "Calloway", "Ibekwe", "Fontaine", "Szabo", "Achterberg",
                               "Navarro"]},
}
# Seeds from 31 up (1-10 tune the detectors, 11-30 are reporting seeds), picked for goals; the data are what the seed made.
# No pair whose kits look alike to colour-blind viewers (red v orange, yellow v white, blue v purple).
FIXTURES = [
    {"id": "northport-valemont", "seed": 7, "home": "northport", "away": "valemont"},
    {"id": "zekteris-thornfield", "seed": 33, "home": "zekteris", "away": "thornfield"},
    {"id": "lornbridge-zekteris", "seed": 37, "home": "lornbridge", "away": "zekteris"},
    {"id": "kingsmoor-valemont", "seed": 47, "home": "kingsmoor", "away": "valemont"},
    {"id": "thornfield-kingsmoor", "seed": 49, "home": "thornfield", "away": "kingsmoor"},
    {"id": "valemont-lornbridge", "seed": 34, "home": "valemont", "away": "lornbridge"},
]
DEFAULT_MATCH = "northport-valemont"


def fixture(match_id: str) -> dict:
    """The fixture with this id; unknown -> the default match."""
    return next((f for f in FIXTURES if f["id"] == match_id), next(f for f in FIXTURES if f["id"] == DEFAULT_MATCH))
