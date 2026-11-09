"""Mesa de xadrez em pixel art: modos Jogo e Livre, animações e placar."""
from __future__ import annotations

import math

import pygame

from . import chess_rules as cr
from .fx import ease_out_back
from .pixelart import OUTLINE, draw_tiny, piece_sprites, silhouette
from .scene_base import SceneBase

SQ = 18           # tamanho da casa em pixels da textura
FR = 9            # largura da moldura
BOARD = 8 * SQ + 2 * FR
TRAY_W = 2 * SQ + 8
GAP = 6
TEX_W = TRAY_W + GAP + BOARD + GAP + TRAY_W
TEX_H = BOARD
BOARD_X = TRAY_W + GAP

LIGHT = (232, 214, 176)
DARK = (176, 112, 82)
FRAME = (86, 50, 46)
FRAME_HI = (124, 76, 64)
FELT = (46, 104, 84)
FELT_DARK = (34, 78, 64)
LAST = (246, 214, 92)
SELECT = (255, 238, 120)
CHECK = (254, 72, 72)
MOVE = (90, 230, 140)

TRAY_FILES = (-3, -2, 9, 10)
MOVE_TIME = 0.30
LAND_TIME = 0.22
COLOR_PT = {"w": "Brancas", "b": "Pretas"}


def standard_free_layout():
    pos = cr.Position()
    return {(cr.file_of(i), cr.rank_of(i)): p for i, p in enumerate(pos.board) if p}


def _tint(surf, rect, color, alpha):
    t = pygame.Surface(rect[2:], pygame.SRCALPHA)
    t.fill((*color, alpha))
    surf.blit(t, rect[:2])


class ChessScene(SceneBase):
    name = "Xadrez"
    theme = ((0.87, 0.27, 0.23), (0.0, 0.42, 0.71), (0.09, 0.10, 0.16))
    tex_size = (TEX_W, TEX_H)

    def __init__(self):
        super().__init__()
        self.sprites = piece_sprites()
        self.glow = {k: silhouette(s, (255, 250, 200)) for k, s in self.sprites.items()}
        self.game = cr.ChessGame()
        self.free = standard_free_layout()
        self.held = None              # (peça, célula de origem) no modo livre
        self.selected = None
        self.pending_promo = None
        self.flipped = False
        self.anims = {}               # célula -> (origem, t0)
        self.lands = {}               # célula -> t0 (quique ao pousar)
        self.tally = {"w": 0.0, "b": 0.0}
        self.counted = None
        self._static = {}

    # ------------------------------------------------------------ geometria
    def _disp(self, cell):
        f, r = cell
        return (7 - f, 7 - r) if self.flipped else (f, r)

    def cell_xy(self, cell):
        """Canto superior esquerdo da célula na textura."""
        f, r = self._disp(cell)
        y = FR + (7 - r) * SQ
        if 0 <= f < 8:
            x = BOARD_X + FR + f * SQ
        elif f < 0:
            x = 4 + (f + 3) * SQ
        else:
            x = BOARD_X + BOARD + GAP + 4 + (f - 9) * SQ
        return x, y

    def cell_center(self, cell):
        x, y = self.cell_xy(cell)
        return x + SQ / 2, y + SQ / 2

    def pick_tex(self, px, py):
        r = 7 - math.floor((py - FR) / SQ)
        if not 0 <= r < 8:
            return None
        if BOARD_X + FR <= px < BOARD_X + FR + 8 * SQ:
            f = math.floor((px - BOARD_X - FR) / SQ)
        elif 4 <= px < 4 + 2 * SQ:
            f = math.floor((px - 4) / SQ) - 3
        elif BOARD_X + BOARD + GAP + 4 <= px < BOARD_X + BOARD + GAP + 4 + 2 * SQ:
            f = math.floor((px - BOARD_X - BOARD - GAP - 4) / SQ) + 9
        else:
            return None
        return self._disp((f, r))   # _disp é a sua própria inversa

    # ------------------------------------------------------------ estado
    def layout(self):
        if self.mode == "livre":
            return dict(self.free)
        out = {}
        for i, p in enumerate(self.game.pos.board):
            if p:
                out[(cr.file_of(i), cr.rank_of(i))] = p
        for color, files in (("w", (9, 10)), ("b", (-2, -3))):
            for k, p in enumerate(self.game.captured_by(color)):
                if k < 16:
                    out[(files[k // 8], k % 8)] = p
        return out

    def free_position(self, turn="w"):
        board = [None] * 64
        for (f, r), p in self.free.items():
            if 0 <= f < 8:
                board[cr.sq(f, r)] = p
        return cr.Position(board, turn, cr.infer_castling(board), None, 0, 1)

    # ------------------------------------------------------------ comandos
    def toggle_mode(self):
        if self.mode == "jogo":
            self.mode = "livre"
            self.free = self.layout()
            self.selected = None
            self.pending_promo = None
            self.toast("Modo livre: mova qualquer peça")
        else:
            self._return_held()
            self.mode = "jogo"
            self.toast("Modo jogo: regras oficiais")

    def flip(self):
        self.flipped = not self.flipped

    def start_from_free(self, turn):
        self._return_held()
        pos = self.free_position(turn)
        err = cr.validate_position(pos)
        if err:
            self.toast(err)
            self.emit("shake", 3)
            return
        self.game = cr.ChessGame(pos)
        self.counted = None
        self.mode = "jogo"
        self.anims.clear()
        self.emit("banner", "VALENDO!", (255, 214, 90))
        self.toast(f"Vez das {COLOR_PT[turn]}")

    def reset(self):
        if self.mode == "livre":
            self.free = standard_free_layout()
            self.held = None
            self.toast("Peças na posição inicial")
        else:
            self.game = cr.ChessGame()
            self.counted = None
            self.selected = None
            self.pending_promo = None
            self.anims.clear()
            self.emit("banner", "NOVA PARTIDA", (255, 214, 90))
        self.emit("sheen")

    def undo(self):
        if self.mode == "livre":
            return
        self.pending_promo = None
        self.selected = None
        if self.game.undo():
            self._sync_tally()
            self.anims.clear()
            self.toast("Lance desfeito")

    def _sync_tally(self):
        res = self.game.result
        if res == self.counted:
            return
        for r, sign in ((self.counted, -1), (res, 1)):
            if r == "1-0":
                self.tally["w"] += sign
            elif r == "0-1":
                self.tally["b"] += sign
            elif r:
                self.tally["w"] += 0.5 * sign
                self.tally["b"] += 0.5 * sign
        self.counted = res

    def _return_held(self):
        if self.held:
            piece, origin = self.held
            target = origin if origin and origin not in self.free else self._free_tray_cell(piece[0])
            if target:
                self.free[target] = piece
            self.held = None

    def _free_tray_cell(self, color):
        files = (-2, -3) if color == "b" else (9, 10)
        for f in files + tuple(f for f in TRAY_FILES if f not in files):
            for r in range(8):
                if (f, r) not in self.free:
                    return (f, r)
        return None

    # ------------------------------------------------------------ entrada
    def click(self, cell, shift=False):
        if self.mode == "livre":
            self._click_free(cell)
        else:
            self._click_game(cell)

    def _click_free(self, cell):
        if cell is None:
            return
        here = self.free.get(cell)
        if self.held:
            piece, _ = self.held
            self.free[cell] = piece
            self.lands[cell] = self.time
            x, y = self.cell_center(cell)
            self.particles.dust(x, y + 7)
            self.held = (here, cell) if here else None
        elif here:
            self.held = (here, cell)
            del self.free[cell]

    def _click_game(self, cell):
        g = self.game
        if self.pending_promo or g.result:
            return
        if cell is None or not (0 <= cell[0] < 8):
            self.selected = None
            return
        s = cr.sq(*cell)
        piece = g.pos.board[s]
        if self.selected is not None and any(m.to == s for m in g.moves_from(self.selected)):
            frm = self.selected
            if g.needs_promotion(frm, s):
                self.pending_promo = (frm, s)
                self.toast("Promoção! 1 Dama  2 Torre  3 Bispo  4 Cavalo")
                return
            self._play(g.find_move(frm, s))
            return
        if piece and piece[0] == g.pos.turn and g.moves_from(s):
            self.selected = s
        elif piece and piece[0] == g.pos.turn:
            self.selected = None
            self.toast("Essa peça não tem lances")
            self.emit("shake", 1.5)
        else:
            self.selected = None

    def _play(self, move):
        g = self.game
        mover = g.pos.turn
        k = len(g.captured_by(mover))
        cap_sq = move.to
        if move.en_passant:
            cap_sq = cr.sq(cr.file_of(move.to), cr.rank_of(move.frm))
        captured = g.push(move)
        self.selected = None
        self.anims.clear()

        def cell(s):
            return (cr.file_of(s), cr.rank_of(s))

        self.anims[cell(move.to)] = (cell(move.frm), self.time)
        if move.castle:
            rank = cr.rank_of(move.frm)
            if cr.file_of(move.to) == 6:
                self.anims[(5, rank)] = ((7, rank), self.time)
            else:
                self.anims[(3, rank)] = ((0, rank), self.time)
        if captured:
            x, y = self.cell_center(cell(cap_sq))
            self.particles.burst_sprite(self.sprites[captured], x, y)
            files = (9, 10) if mover == "w" else (-2, -3)
            if k < 16:
                self.anims[(files[k // 8], k % 8)] = (cell(cap_sq), self.time)
            val = cr.PIECE_VALUES[captured[1]]
            self.emit("popup", f"+{val}", (90, 170, 255) if mover == "w" else (255, 90, 90), (x, y))
            self.emit("shake", 2 + val * 0.6)
        if move.promo:
            self.emit("banner", "PROMOÇÃO!", (255, 214, 90))
        self._sync_tally()
        if g.result:
            if g.reason == "Xeque-mate":
                self.emit("banner", "XEQUE-MATE!", (255, 90, 90))
                self.emit("confetti")
                self.emit("shake", 8)
            else:
                self.emit("banner", "EMPATE", (200, 200, 255))
            self.toast(self.result_text())
        elif g.pos.in_check():
            self.emit("banner", "XEQUE!", (255, 90, 90))
            self.emit("shake", 4)

    def key(self, key, mod):
        shift = bool(mod & pygame.KMOD_SHIFT)
        if self.pending_promo:
            promo = {pygame.K_1: "Q", pygame.K_2: "R", pygame.K_3: "B", pygame.K_4: "N",
                     pygame.K_KP1: "Q", pygame.K_KP2: "R", pygame.K_KP3: "B", pygame.K_KP4: "N"}.get(key)
            if promo:
                frm, to = self.pending_promo
                self.pending_promo = None
                self._play(self.game.find_move(frm, to, promo))
            elif key == pygame.K_ESCAPE:
                self.pending_promo = None
                self.selected = None
            return True
        if key == pygame.K_ESCAPE:
            if self.held:
                self._return_held()
                return True
            if self.selected is not None:
                self.selected = None
                return True
            return False
        if key == pygame.K_g and self.mode == "jogo":
            if not self.game.result:
                loser = self.game.pos.turn
                self.game.resign(loser)
                self._sync_tally()
                self.emit("banner", "DESISTÊNCIA", (255, 150, 90))
                self.toast(self.result_text())
            return True
        if self.mode == "livre":
            kinds = {pygame.K_1: "P", pygame.K_2: "N", pygame.K_3: "B", pygame.K_4: "R",
                     pygame.K_5: "Q", pygame.K_6: "K"}
            if key in kinds:
                self._return_held()
                color = "b" if shift else "w"
                self.held = ((color, kinds[key]), None)
                return True
            if key == pygame.K_c and self.held:
                (color, kind), origin = self.held
                self.held = ((cr.other(color), kind), origin)
                return True
            if key in (pygame.K_DELETE, pygame.K_BACKSPACE) and self.held:
                cx, cy = self.cell_center(self.hover) if self.hover else (TEX_W / 2, TEX_H / 2)
                self.particles.burst_sprite(self.sprites[self.held[0]], cx, cy, 40)
                self.held = None
                return True
            if key == pygame.K_x:
                self._return_held()
                self.free = {}
                pieces = sorted(standard_free_layout().values(), key=lambda p: -cr.PIECE_VALUES[p[1]])
                for p in pieces:
                    c = self._free_tray_cell(p[0])
                    if c:
                        self.free[c] = p
                self.emit("sheen")
                self.toast("Tabuleiro vazio: peças nas bandejas")
                return True
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.start_from_free("b" if shift else "w")
                return True
        return False

    def held_sprite(self):
        return self.sprites[self.held[0]] if self.held else None

    # ------------------------------------------------------------ desenho
    def update(self, dt):
        super().update(dt)
        for c, (_s, t0) in list(self.anims.items()):
            if self.time - t0 > MOVE_TIME:
                del self.anims[c]
                self.lands[c] = self.time
                x, y = self.cell_center(c)
                self.particles.dust(x, y + 7, n=5)
        for c, t0 in list(self.lands.items()):
            if self.time - t0 > LAND_TIME:
                del self.lands[c]

    def _static_surface(self):
        key = self.flipped
        if key in self._static:
            return self._static[key]
        s = pygame.Surface((TEX_W, TEX_H), pygame.SRCALPHA)
        # bandejas de feltro
        for x0 in (0, BOARD_X + BOARD + GAP):
            pygame.draw.rect(s, FRAME, (x0, 0, TRAY_W, TEX_H))
            pygame.draw.rect(s, FRAME_HI, (x0, 0, TRAY_W, 1))
            pygame.draw.rect(s, FELT_DARK, (x0 + 3, 3, TRAY_W - 6, TEX_H - 6))
            pygame.draw.rect(s, FELT, (x0 + 4, 4, TRAY_W - 8, TEX_H - 8))
            for yy in range(6, TEX_H - 6, 4):
                for xx in range(x0 + 6 + (yy // 4) % 2 * 2, x0 + TRAY_W - 6, 4):
                    s.set_at((xx, yy), FELT_DARK)
        # moldura
        pygame.draw.rect(s, FRAME, (BOARD_X, 0, BOARD, BOARD))
        pygame.draw.rect(s, FRAME_HI, (BOARD_X, 0, BOARD, 1))
        pygame.draw.rect(s, FRAME_HI, (BOARD_X, 0, 1, BOARD))
        pygame.draw.rect(s, OUTLINE, (BOARD_X + FR - 1, FR - 1, 8 * SQ + 2, 8 * SQ + 2))
        for f in range(8):
            for r in range(8):
                x, y = self.cell_xy((f, r))
                light = (f + r) % 2 == 1
                pygame.draw.rect(s, LIGHT if light else DARK, (x, y, SQ, SQ))
                for k in range(3):   # veios de madeira em pixels
                    yy = y + 3 + k * 6 + (f * 3 + r) % 3
                    col = (220, 200, 160) if light else (160, 100, 74)
                    pygame.draw.line(s, col, (x + 2 + (r + k) % 4, yy), (x + 7 + (f + k) % 6, yy))
        lab = (226, 190, 130)
        for f in range(8):
            x, _ = self.cell_center((f, 0))
            draw_tiny(s, "ABCDEFGH"[f], int(x) - 1, BOARD - FR + 2, lab)
        for r in range(8):
            _, y = self.cell_center((0, r))
            draw_tiny(s, str(r + 1), BOARD_X + 3, int(y) - 2, lab)
        self._static[key] = s
        return s

    def draw_board(self, surf):
        surf.blit(self._static_surface(), (0, 0))
        g, t = self.game, self.time
        if self.mode == "jogo":
            last = g.last_move()
            if last:
                for s in (last.frm, last.to):
                    _tint(surf, (*self.cell_xy((cr.file_of(s), cr.rank_of(s))), SQ, SQ), LAST, 90)
            if g.pos.in_check() and not g.result:
                k = g.pos.king_square(g.pos.turn)
                _tint(surf, (*self.cell_xy((cr.file_of(k), cr.rank_of(k))), SQ, SQ), CHECK,
                      int(120 + 80 * math.sin(t * 8)))
            if self.selected is not None:
                s = self.selected
                _tint(surf, (*self.cell_xy((cr.file_of(s), cr.rank_of(s))), SQ, SQ), SELECT, 120)
        if self.hover:
            x, y = self.cell_xy(self.hover)
            col = SELECT if (self.held or self.selected is not None) else (255, 255, 255)
            b = 1 if int(t * 4) % 2 else 0
            pygame.draw.rect(surf, col, (x - b, y - b, SQ + 2 * b, SQ + 2 * b), 1)

        sel_cell = None
        if self.mode == "jogo" and self.selected is not None:
            sel_cell = (cr.file_of(self.selected), cr.rank_of(self.selected))
        for cell, piece in sorted(self.layout().items(), key=lambda kv: self.cell_xy(kv[0])[1]):
            cx, cy = self.cell_center(cell)
            lift, sx, sy = 0.0, 1.0, 1.0
            if cell in self.anims:
                src, t0 = self.anims[cell]
                k = ease_out_back((t - t0) / MOVE_TIME, 1.2)
                ax, ay = self.cell_center(src)
                cx, cy = ax + (cx - ax) * k, ay + (cy - ay) * k
                lift = math.sin(math.pi * min(1.0, (t - t0) / MOVE_TIME)) * 7
            elif cell in self.lands:
                k = (t - self.lands[cell]) / LAND_TIME
                q = math.sin(math.pi * k) * 0.25
                sx, sy = 1 + q, 1 - q
            if cell == sel_cell:
                lift = 3 + math.sin(t * 6) * 1.5
            elif cell == self.hover and self.mode == "jogo" and piece[0] == g.pos.turn and not g.result:
                lift = 1.5
            self._draw_piece(surf, piece, cx, cy, lift, sx, sy, glow=(cell == sel_cell))

        if self.mode == "jogo" and self.selected is not None:
            for m in g.moves_from(self.selected):
                c = (cr.file_of(m.to), cr.rank_of(m.to))
                if g.pos.board[m.to] or m.en_passant:
                    x0, y0 = self.cell_xy(c)
                    for dx, dy in ((0, 0), (SQ - 4, 0), (0, SQ - 4), (SQ - 4, SQ - 4)):
                        pygame.draw.rect(surf, CHECK, (x0 + dx, y0 + dy, 4, 4))
                        pygame.draw.rect(surf, OUTLINE, (x0 + dx, y0 + dy, 4, 4), 1)
                else:
                    x, y = self.cell_center(c)
                    r = 2 + (1 if int(t * 5) % 2 else 0)
                    pygame.draw.rect(surf, OUTLINE, (int(x) - r - 1, int(y) - r - 1, 2 * r + 2, 2 * r + 2))
                    pygame.draw.rect(surf, MOVE, (int(x) - r, int(y) - r, 2 * r, 2 * r))
        self.particles.draw(surf)

    def _draw_piece(self, surf, piece, cx, cy, lift=0.0, sx=1.0, sy=1.0, glow=False):
        spr = self.sprites[piece]
        w, h = spr.get_size()
        if sx != 1.0 or sy != 1.0:
            spr = pygame.transform.scale(spr, (max(1, round(w * sx)), max(1, round(h * sy))))
        sw, sh = spr.get_size()
        base_y = cy + SQ / 2 - 1
        shw = max(4, int(12 - lift * 0.6))
        _tint(surf, (round(cx - shw / 2), round(base_y - 2), shw, 3), (20, 10, 20), 110)
        x = round(cx - sw / 2)
        y = round(base_y - sh - lift)
        if glow:
            gl = self.glow[piece]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                surf.blit(gl, (x + dx, y + dy))
        surf.blit(spr, (x, y))

    # ------------------------------------------------------------ HUD
    def result_text(self):
        g = self.game
        if not g.result:
            return ""
        if g.result == "1-0":
            return f"{g.reason}: Brancas vencem"
        if g.result == "0-1":
            return f"{g.reason}: Pretas vencem"
        return f"Empate: {g.reason}"

    def hud(self):
        g = self.game
        d = {"title": "XADREZ", "mode": "Modo Jogo" if self.mode == "jogo" else "Modo Livre",
             "accent": (254, 95, 85), "lines": [], "icons": None,
             "tally": ("PARTIDAS", f"{self.tally['w']:g}", f"{self.tally['b']:g}")}
        if self.mode == "jogo":
            sc = g.score()
            d["scores"] = [("BRANCAS", sc["w"], (0, 147, 255)), ("PRETAS", sc["b"], (254, 76, 64))]
            if g.result:
                win = {"1-0": "Brancas vencem!", "0-1": "Pretas vencem!"}.get(g.result, "Empate!")
                d["status"] = (win, (255, 214, 90))
                d["lines"].append((g.reason, (255, 214, 90)))
            elif g.pos.in_check():
                d["status"] = (f"Vez das {COLOR_PT[g.pos.turn]}: XEQUE!", (255, 120, 110))
            else:
                d["status"] = (f"Vez das {COLOR_PT[g.pos.turn]}", (255, 255, 255))
            diff = sc["diff"]
            d["lines"].append(("Vantagem: " + ("igual" if diff == 0 else
                               (f"Brancas +{diff}" if diff > 0 else f"Pretas +{-diff}")), (200, 210, 230)))
            d["icons"] = (g.captured_by("w"), g.captured_by("b"))
            for line in g.move_list()[-3:]:
                d["lines"].append((line, (170, 176, 200)))
            if self.pending_promo:
                d["lines"].append(("PROMOÇÃO: 1 D  2 T  3 B  4 C", (255, 230, 120)))
            d["hints"] = [("Clique", "mover"), ("G", "desistir"), ("Z", "desfazer"), ("R", "nova"),
                          ("M", "livre")]
        else:
            pos = self.free_position()
            d["scores"] = [("BRANCAS", pos.material("w"), (0, 147, 255)),
                           ("PRETAS", pos.material("b"), (254, 76, 64))]
            d["status"] = ("Monte a posição que quiser", (255, 255, 255))
            err = cr.validate_position(pos)
            if err:
                d["lines"].append((err, (240, 160, 160)))
            else:
                d["lines"].append(("Enter: jogar desta posição", (150, 240, 170)))
                d["lines"].append(("Shift+Enter: pretas começam", (150, 200, 170)))
            d["hints"] = [("Clique", "pegar/soltar"), ("1-6", "peça"), ("Shift", "preta"),
                          ("C", "cor"), ("Del", "apagar"), ("X", "esvaziar"), ("R", "inicial"),
                          ("M", "jogo")]
        return d
