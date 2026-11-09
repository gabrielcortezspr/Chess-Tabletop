"""Pixel art gerada por código: peças de xadrez, pedras de Go e fonte 3x5.

As peças são desenhadas a partir de máscaras ASCII. O contorno escuro e o
sombreamento (luz em cima/esquerda, sombra embaixo/direita) são automáticos.
"""
from __future__ import annotations

import pygame

OUTLINE = (20, 16, 30)

# máscaras 14x14 ('.' vazio, '#' corpo, 'a' faixa de cor, 'g' ouro, 'e' olho)
PIECE_MASKS = {
    "P": [
        "..............",
        "..............",
        "......##......",
        ".....####.....",
        "....######....",
        "....######....",
        ".....####.....",
        "....aaaaaa....",
        ".....####.....",
        ".....####.....",
        "....######....",
        "...aaaaaaaa...",
        "..##########..",
        "..##########..",
    ],
    "R": [
        "..............",
        "..##.##.##.##.",
        "..##########..",
        "..##########..",
        "...########...",
        "...aaaaaaaa...",
        "....######....",
        "....######....",
        "....######....",
        "....######....",
        "...########...",
        "..aaaaaaaaaa..",
        ".############.",
        ".############.",
    ],
    "N": [
        "......#.#.....",
        ".....######...",
        "....########..",
        "...##e#######.",
        "..###########.",
        ".#####...####.",
        ".####...#####.",
        "......######..",
        ".....#######..",
        "....########..",
        "...aaaaaaaaa..",
        "...#########..",
        "..###########.",
        "..###########.",
    ],
    "B": [
        "......gg......",
        "......##......",
        ".....####.....",
        "....##.###....",
        "....#.####....",
        "....######....",
        ".....####.....",
        "....aaaaaa....",
        ".....####.....",
        ".....####.....",
        "....######....",
        "...aaaaaaaa...",
        "..##########..",
        "..##########..",
    ],
    "Q": [
        "..g..g..g..g..",
        "..#..#..#..#..",
        "..##.##.##.#..",
        "..##########..",
        "...########...",
        "....aaaaaa....",
        ".....####.....",
        ".....####.....",
        "....######....",
        "....######....",
        "...########...",
        "..aaaaaaaaaa..",
        ".############.",
        ".############.",
    ],
    "K": [
        "......gg......",
        ".....gggg.....",
        "......gg......",
        "....######....",
        "...########...",
        "...########...",
        "....######....",
        "....aaaaaa....",
        ".....####.....",
        ".....####.....",
        "....######....",
        "...aaaaaaaa...",
        ".############.",
        ".############.",
    ],
}

PALETTES = {
    "w": {"#": (238, 230, 210), "a": (74, 150, 232), "g": (252, 200, 64), "e": (20, 16, 30)},
    "b": {"#": (78, 70, 98), "a": (232, 70, 76), "g": (252, 200, 64), "e": (255, 120, 90)},
}


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def sprite_from_mask(mask, palette, mirror=False):
    rows = [r[::-1] for r in mask] if mirror else mask
    h, w = len(rows), len(rows[0])
    surf = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)

    def filled(x, y):
        return 0 <= y < h and 0 <= x < w and rows[y][x] != "."

    for y in range(-1, h + 1):
        for x in range(-1, w + 1):
            if filled(x, y):
                tag = rows[y][x]
                base = palette.get(tag, palette["#"])
                k = 1.0
                if not filled(x - 1, y) or not filled(x, y - 1):
                    k = 1.18
                elif not filled(x + 1, y) or not filled(x, y + 1):
                    k = 0.78
                if tag == "e":
                    k = 1.0
                surf.set_at((x + 1, y + 1), _shade(base, k))
            elif any(filled(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                surf.set_at((x + 1, y + 1), OUTLINE)
    return surf


def piece_sprites():
    """{(cor, tipo): Surface 16x16}"""
    out = {}
    for color in ("w", "b"):
        for kind, mask in PIECE_MASKS.items():
            out[(color, kind)] = sprite_from_mask(mask, PALETTES[color], mirror=(color == "b" and kind == "N"))
    return out


def silhouette(sprite, color):
    """Mesma forma do sprite, numa cor só (para sombras/brilho)."""
    s = sprite.copy()
    s.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MIN)
    s.fill((*color, 0), special_flags=pygame.BLEND_RGBA_MAX)
    return s


def stone_sprite(d, color):
    """Pedra de Go em pixel art com diâmetro `d` pixels."""
    surf = pygame.Surface((d, d), pygame.SRCALPHA)
    c = (d - 1) / 2
    r2 = (d / 2) ** 2 - 0.2
    if color == "b":
        base, light, dark = (44, 42, 58), (104, 100, 130), (24, 22, 34)
    else:
        base, light, dark = (238, 236, 226), (255, 255, 255), (178, 172, 160)
    for y in range(d):
        for x in range(d):
            dx, dy = x - c, y - c
            dist2 = dx * dx + dy * dy
            if dist2 > r2:
                continue
            edge = dist2 > (d / 2 - 1.1) ** 2
            if edge:
                col = OUTLINE
            elif dx + dy > d * 0.35:
                col = dark
            elif (dx + d * 0.18) ** 2 + (dy + d * 0.18) ** 2 < (d * 0.16) ** 2 + 0.6:
                col = light
            else:
                col = base
            surf.set_at((x, y), col)
    return surf


# ------------------------------------------------------------------ fonte 3x5
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


def tiny_width(text):
    return max(0, len(text) * 4 - 1)


def draw_tiny(surf, text, x, y, color):
    """Texto na fonte 3x5 com o canto superior esquerdo em (x, y)."""
    cx = x
    for ch in text.upper():
        glyph = FONT_3X5.get(ch)
        if glyph:
            for r, line in enumerate(glyph):
                for c, v in enumerate(line):
                    if v == "#":
                        surf.set_at((cx + c, y + r), color)
        cx += 4
