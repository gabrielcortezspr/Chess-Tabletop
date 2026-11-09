"""Modelos voxel (cubinhos) gerados por código para as peças e objetos.

Cada modelo é um par de arrays numpy:
    pos   (N, 3) centros dos voxels em unidades de voxel (y = 0 é a base)
    color (N, 3) cor RGB 0..1
Somente voxels com alguma face exposta são mantidos (economiza GPU).
"""
from __future__ import annotations

import math

import numpy as np

# paletas
WHITE_PIECE = (0.93, 0.86, 0.70)
WHITE_ACCENT = (0.80, 0.66, 0.44)
BLACK_PIECE = (0.20, 0.18, 0.23)
BLACK_ACCENT = (0.42, 0.30, 0.52)
GOLD = (0.98, 0.78, 0.26)


def _rng_noise(n, seed, amount):
    rng = np.random.default_rng(seed)
    return 1.0 + (rng.random(n) - 0.5) * 2 * amount


class VoxelGrid:
    def __init__(self):
        self.vox: dict = {}   # (x, y, z) -> tag

    def put(self, x, y, z, tag="body"):
        self.vox[(int(x), int(y), int(z))] = tag

    def remove(self, x, y, z):
        self.vox.pop((int(x), int(y), int(z)), None)

    def disc(self, y, r, tag="body", hollow=0.0):
        R = int(math.ceil(r))
        for x in range(-R, R + 1):
            for z in range(-R, R + 1):
                d2 = x * x + z * z
                if d2 <= r * r + 0.35 and d2 >= hollow * hollow:
                    self.put(x, y, z, tag)

    def lathe(self, radii, y0=0, tag="body"):
        for i, r in enumerate(radii):
            if r > 0:
                self.disc(y0 + i, r, tag)
        return y0 + len(radii)

    def to_arrays(self, palette: dict, seed=0, noise=0.05):
        keys = list(self.vox.keys())
        filled = set(keys)
        keep = []
        for k in keys:
            x, y, z = k
            if y == 0:
                # base apoiada na mesa: só precisa se tiver vizinho lateral vazio
                pass
            nb = ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1))
            if any(n not in filled for n in nb):
                keep.append(k)
        pos = np.array(keep, dtype=np.float32).reshape(-1, 3)
        col = np.array([palette[self.vox[k]] for k in keep], dtype=np.float32).reshape(-1, 3)
        col *= _rng_noise(len(keep), seed, noise)[:, None]
        return pos, np.clip(col, 0, 1)


BASE = [5.4, 5.4, 4.7, 4.1]


def _ring_with_gaps(g: VoxelGrid, y, r_out, r_in, gaps, tag="body"):
    R = int(math.ceil(r_out))
    for x in range(-R, R + 1):
        for z in range(-R, R + 1):
            d2 = x * x + z * z
            if r_in * r_in <= d2 <= r_out * r_out + 0.35:
                ang = (math.degrees(math.atan2(z, x)) + 360 + 22.5) % 360
                if int(ang // (360 / gaps)) % 2 == 0:
                    g.put(x, y, z, tag)


def pawn():
    g = VoxelGrid()
    y = g.lathe(BASE)
    y = g.lathe([3.2, 2.6, 2.3, 2.2, 2.2], y)
    y = g.lathe([3.4], y, "accent")
    y = g.lathe([2.4, 2.9, 3.2, 3.3, 3.2, 2.9, 2.2, 1.2], y)
    return g


def rook():
    g = VoxelGrid()
    y = g.lathe(BASE)
    y = g.lathe([3.8, 3.4, 3.2, 3.2, 3.2, 3.2, 3.2, 3.3, 3.5], y)
    y = g.lathe([4.2], y, "accent")
    y = g.lathe([4.2, 4.2], y)
    for i in range(3):
        _ring_with_gaps(g, y + i, 4.2, 2.4, 8)
    return g


def bishop():
    g = VoxelGrid()
    y = g.lathe(BASE)
    y = g.lathe([3.4, 2.8, 2.5, 2.3, 2.2, 2.2], y)
    y = g.lathe([3.5], y, "accent")
    y0 = y
    y = g.lathe([2.4, 2.8, 3.1, 3.2, 3.2, 3.0, 2.7, 2.3, 1.8, 1.2], y)
    # fenda diagonal na mitra
    for (x, yy, z) in list(g.vox.keys()):
        if y0 + 4 <= yy <= y0 + 8 and abs((x + (yy - y0 - 4)) - 1) <= 0 and z <= 0:
            g.remove(x, yy, z)
    g.lathe([1.2, 1.6, 1.2], y, "accent")
    return g


def queen():
    g = VoxelGrid()
    y = g.lathe(BASE)
    y = g.lathe([3.8, 3.2, 2.8, 2.6, 2.5, 2.4, 2.4, 2.5], y)
    y = g.lathe([3.7], y, "accent")
    y = g.lathe([2.8, 3.0, 3.3, 3.6, 3.9], y)
    for i in range(2):
        _ring_with_gaps(g, y + i, 4.1, 2.5, 10, "accent")
    g.lathe([2.6, 1.6], y)
    g.lathe([1.3, 1.6, 1.3], y + 2, "gold")
    return g


def king():
    g = VoxelGrid()
    y = g.lathe(BASE)
    y = g.lathe([3.9, 3.3, 3.0, 2.8, 2.7, 2.6, 2.6, 2.6, 2.7], y)
    y = g.lathe([3.9], y, "accent")
    y = g.lathe([3.0, 3.2, 3.4, 3.6, 3.7, 3.6], y)
    y = g.lathe([2.4, 1.4], y, "accent")
    # cruz
    for i in range(5):
        g.put(0, y + i, 0, "gold")
    for x in (-1, 1):
        g.put(x, y + 3, 0, "gold")
    return g


KNIGHT_PROFILE = [
    # colunas = z de -5 (nuca) até +4 (focinho); linhas de cima para baixo
    "...#.#....",
    "...#####..",
    "..#######.",
    ".##e######",
    ".####..###",
    ".####...##",
    ".#####....",
    "..#####...",
    "..######..",
    "..#######.",
    ".#######..",
    ".########.",
]


def knight():
    g = VoxelGrid()
    y = g.lathe(BASE)
    y = g.lathe([3.8, 3.5], y)
    rows = len(KNIGHT_PROFILE)
    for ri, row in enumerate(KNIGHT_PROFILE):
        yy = y + (rows - 1 - ri)
        for ci, ch in enumerate(row):
            if ch == ".":
                continue
            z = ci - 5
            width = 2 if ri > 1 else 1
            for x in range(-width, width + 1):
                tag = "body"
                if ch == "e" and abs(x) == width:
                    tag = "eye"
                if ci <= 2 and ri <= 8 and x == 0 and ch != "e":
                    tag = "accent"   # crina
                g.put(x, yy, z, tag)
    # o modelo "olha" para +z; as peças brancas olham para -z (para o lado das pretas)
    flipped = VoxelGrid()
    for (x, yy, z), t in g.vox.items():
        flipped.put(-x, yy, -z, t)
    return flipped


BUILDERS = {"P": pawn, "N": knight, "B": bishop, "R": rook, "Q": queen, "K": king}


def chess_models(voxel_size: float):
    """Retorna {(cor, tipo): (pos, cor)} já em unidades de mundo (base em y=0)."""
    out = {}
    for ci, color in enumerate(("w", "b")):
        pal = {
            "body": WHITE_PIECE if color == "w" else BLACK_PIECE,
            "accent": WHITE_ACCENT if color == "w" else BLACK_ACCENT,
            "gold": GOLD,
            "eye": (0.1, 0.1, 0.1) if color == "w" else (0.95, 0.4, 0.3),
        }
        for ki, kind in enumerate("PNBRQK"):
            g = BUILDERS[kind]()
            pos, col = g.to_arrays(pal, seed=ci * 10 + ki)
            if color == "b":
                pos = pos * np.array([-1, 1, -1], dtype=np.float32)   # gira 180°
            pos = pos * voxel_size + np.array([0, voxel_size / 2, 0], dtype=np.float32)
            out[(color, kind)] = (pos.astype(np.float32), col.astype(np.float32))
    return out


def go_stone(color: str, voxel_size: float):
    g = VoxelGrid()
    g.lathe([3.4, 4.6, 4.9, 4.6, 3.4])
    if color == "b":
        pal = {"body": (0.12, 0.12, 0.15)}
    else:
        pal = {"body": (0.95, 0.94, 0.90)}
    pos, col = g.to_arrays(pal, seed=1 if color == "b" else 2, noise=0.04)
    pos = pos * voxel_size + np.array([0, voxel_size / 2, 0], dtype=np.float32)
    return pos.astype(np.float32), col.astype(np.float32)


def go_bowl(voxel_size: float):
    g = VoxelGrid()
    radii = [6, 8, 9.5, 10.5, 11, 11.2]
    for y, r in enumerate(radii):
        g.disc(y, r, "wood", hollow=(r - 1.6) if y > 0 else 0)
    pos, col = g.to_arrays({"wood": (0.55, 0.33, 0.17)}, seed=7, noise=0.08)
    pos = pos * voxel_size + np.array([0, voxel_size / 2, 0], dtype=np.float32)
    return pos.astype(np.float32), col.astype(np.float32)


# Fonte 3x5 para as coordenadas gravadas na borda do tabuleiro
FONT_3X5 = {
    "A": ["###", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": ["###", "#..", "#..", "#..", "###"], "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"], "F": ["###", "#..", "##.", "#..", "#.."],
    "G": ["###", "#..", "#.#", "#.#", "###"], "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "J": ["..#", "..#", "..#", "#.#", "###"], "K": ["#.#", "#.#", "##.", "#.#", "#.#"],
    "L": ["#..", "#..", "#..", "#..", "###"], "M": ["#.#", "###", "###", "#.#", "#.#"],
    "N": ["##.", "#.#", "#.#", "#.#", "#.#"], "O": ["###", "#.#", "#.#", "#.#", "###"],
    "P": ["###", "#.#", "###", "#..", "#.."], "Q": ["###", "#.#", "#.#", "###", "..#"],
    "R": ["##.", "#.#", "##.", "#.#", "#.#"], "S": ["###", "#..", "###", "..#", "###"],
    "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", "###", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", "..#", "..#", "..#"],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
}


def text_pixels(text: str):
    """Pixels (col, row) de um texto na fonte 3x5; row 0 é o topo."""
    pts = []
    cx = 0
    for ch in text.upper():
        glyph = FONT_3X5.get(ch)
        if glyph:
            for r, line in enumerate(glyph):
                for c, v in enumerate(line):
                    if v == "#":
                        pts.append((cx + c, r))
        cx += 4
    width = max(cx - 1, 0)
    return pts, width
