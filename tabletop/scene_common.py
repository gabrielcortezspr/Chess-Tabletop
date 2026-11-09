"""Peças compartilhadas pelas cenas: mesa, rótulos, utilidades de cor."""
from __future__ import annotations

import numpy as np

from .renderer import InstanceBatch
from .voxels import text_pixels

TABLE_TOP = -0.4

WOOD_TABLE = (0.47, 0.30, 0.18)
WOOD_DARK = (0.30, 0.18, 0.11)
FLOOR = (0.20, 0.16, 0.22)
RUG = (0.42, 0.14, 0.18)


def build_room(batch: InstanceBatch):
    """Mesa de madeira, pernas, chão e tapete."""
    batch.cube((0, TABLE_TOP - 0.3, 0), (30, 0.6, 22), WOOD_TABLE, 1.0)
    batch.cube((0, TABLE_TOP - 0.75, 0), (29, 0.3, 21), WOOD_DARK, 0.6)
    for sx in (-1, 1):
        for sz in (-1, 1):
            batch.cube((sx * 13.8, TABLE_TOP - 4.5, sz * 9.8), (1.0, 7.8, 1.0), WOOD_DARK, 0.8)
    batch.cube((0, -8.5, 0), (120, 0.5, 120), FLOOR, 1.0)
    batch.cube((0, -8.24, 0), (40, 0.04, 32), RUG, 1.0)
    # borda decorativa da mesa
    batch.cube((0, TABLE_TOP - 0.02, 10.9), (30, 0.06, 0.2), WOOD_DARK, 0.5)
    batch.cube((0, TABLE_TOP - 0.02, -10.9), (30, 0.06, 0.2), WOOD_DARK, 0.5)


def add_label(batch: InstanceBatch, text: str, center, pixel: float, color, rotate_deg: int = 0,
              height=0.02):
    """Escreve `text` deitado na superfície, centrado em `center` (x, y, z).

    rotate_deg: 0 = legível de quem está em +z olhando para -z; 180 = do outro lado.
    """
    pts, width = text_pixels(text)
    cx, cy, cz = center
    w, h = width * pixel, 5 * pixel
    for col, row in pts:
        lx = -w / 2 + (col + 0.5) * pixel
        lz = -h / 2 + (row + 0.5) * pixel
        if rotate_deg == 180:
            lx, lz = -lx, -lz
        elif rotate_deg == 90:
            lx, lz = lz, -lx
        elif rotate_deg == 270:
            lx, lz = -lz, lx
        batch.cube((cx + lx, cy + height / 2, cz + lz), (pixel, height, pixel), color, 0.0)


def mix(a, b, t):
    return tuple(float(x) * (1 - t) + float(y) * t for x, y in zip(a, b))


def as_static(batch: InstanceBatch) -> np.ndarray:
    return batch.array().copy()
