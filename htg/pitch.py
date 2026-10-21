"""Pitch geometry shared by every module.

Global frame (used in all files we produce):
    x in [0, 105] metres along the pitch, y in [0, 68] metres across it.
    HOME attacks towards x = 105, AWAY attacks towards x = 0 (no half-time switch in this project).

Attacking frame (used for models such as xT):
    the team in possession always attacks towards x = 105, and y is mirrored for AWAY
    so that "left flank" means the same thing for both teams.
"""
from __future__ import annotations

import numpy as np

LENGTH, WIDTH = 105.0, 68.0
GRID_X, GRID_Y = 12, 8  # xT / transition grid
SB_LENGTH, SB_WIDTH = 120.0, 80.0  # StatsBomb native units (yards-ish)


def from_statsbomb(x: float, y: float) -> tuple[float, float]:
    """StatsBomb: origin top-left, team in possession attacks to the right, y grows downwards.

    Returned in the attacking frame with y growing upwards (left flank = high y).
    """
    return x / SB_LENGTH * LENGTH, WIDTH - y / SB_WIDTH * WIDTH


def to_attacking(x: float, y: float, team: str) -> tuple[float, float]:
    """Global -> attacking frame for the given team ("HOME" or "AWAY")."""
    if team == "HOME":
        return x, y
    return LENGTH - x, WIDTH - y


def to_global(xa: float, ya: float, team: str) -> tuple[float, float]:
    """Attacking frame -> global frame (the transform is its own inverse)."""
    return to_attacking(xa, ya, team)


def zone_of(xa: float, ya: float) -> int:
    """Grid cell index (row-major, 0..GRID_X*GRID_Y-1) for an attacking-frame position."""
    i = int(np.clip(xa / LENGTH * GRID_X, 0, GRID_X - 1))
    j = int(np.clip(ya / WIDTH * GRID_Y, 0, GRID_Y - 1))
    return i * GRID_Y + j


def zone_center(z: int) -> tuple[float, float]:
    i, j = divmod(z, GRID_Y)
    return (i + 0.5) * LENGTH / GRID_X, (j + 0.5) * WIDTH / GRID_Y


def sample_in_zone(z: int, rng: np.random.Generator) -> tuple[float, float]:
    i, j = divmod(z, GRID_Y)
    return ((i + rng.random()) * LENGTH / GRID_X, (j + rng.random()) * WIDTH / GRID_Y)


def flank_pan(xa: float, ya: float) -> float:
    """-1 = attacker's left flank, +1 = attacker's right flank (attacking frame, left = high y)."""
    return float(np.clip(-(ya - WIDTH / 2) / (WIDTH / 2), -1.0, 1.0))
