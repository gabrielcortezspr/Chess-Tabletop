"""Cena do xadrez: tabuleiro, peças voxel, interação nos modos Jogo e Livre."""
from __future__ import annotations

import math

import numpy as np
import pygame

from . import chess_rules as cr
from .renderer import InstanceBatch, arc, smoothstep
from .scene_common import TABLE_TOP, add_label, as_static, build_room, mix
from .voxels import chess_models

VOX = 1.0 / 15.0
LIGHT_SQ = (0.86, 0.76, 0.58)
DARK_SQ = (0.45, 0.28, 0.17)
FRAME = (0.26, 0.15, 0.09)
TRAY = (0.33, 0.20, 0.12)
SEL = (0.98, 0.85, 0.30)
LAST = (0.70, 0.80, 0.35)
CHECK = (0.95, 0.25, 0.20)
HOVER = (1.0, 1.0, 1.0)
MOVE_DOT = (0.35, 0.95, 0.55)
CAPTURE_MARK = (1.0, 0.35, 0.30)

TRAY_FILES = (-3, -2, 9, 10)
TRAY_Y = TABLE_TOP + 0.08
ANIM_TIME = 0.32

COLOR_PT = {"w": "Brancas", "b": "Pretas"}


def cell_center(cell):
    f, r = cell
    y = 0.0 if 0 <= f < 8 else TRAY_Y
    return np.array([f - 3.5, y, 3.5 - r], dtype=np.float32)


def world_to_cell(p):
    if p is None:
        return None
    f = math.floor(p[0] + 4)
    r = math.floor(4 - p[2])
    if 0 <= r < 8 and (0 <= f < 8 or f in TRAY_FILES):
        return (f, r)
    return None


def standard_free_layout():
    pos = cr.Position()
    return {(cr.file_of(i), cr.rank_of(i)): p for i, p in enumerate(pos.board) if p}


class ChessScene:
    name = "Xadrez"
    focus_radius = 6.5

    def __init__(self):
        self.models = chess_models(VOX)
        self.game = cr.ChessGame()
        self.mode = "jogo"            # "jogo" | "livre"
        self.free = standard_free_layout()
        self.held = None              # (peça, célula de origem) no modo livre
        self.selected = None          # casa selecionada no modo jogo
        self.pending_promo = None     # (frm, to)
        self.hover = None
        self.anims = {}               # célula destino -> (célula origem, t0)
        self.time = 0.0
        self.tally = {"w": 0.0, "b": 0.0}
        self.counted = None           # resultado já somado ao placar
        self.message = ("", 0.0)
        self.static = self._build_static()

    # ------------------------------------------------------------ utilidades
    def toast(self, text):
        self.message = (text, self.time)

    def _build_static(self):
        b = InstanceBatch()
        build_room(b)
        # moldura do tabuleiro
        b.cube((0, TABLE_TOP / 2 - 0.02, 0), (9.3, -TABLE_TOP - 0.04, 9.3), FRAME, 0.7)
        b.cube((0, -0.07, 0), (8.12, 0.06, 8.12), (0.15, 0.09, 0.05), 0.0)
        # coordenadas gravadas na moldura
        label = (0.88, 0.74, 0.45)
        for f in range(8):
            ch = "ABCDEFGH"[f]
            add_label(b, ch, (f - 3.5, -0.04, 4.33), 0.085, label)
            add_label(b, ch, (f - 3.5, -0.04, -4.33), 0.085, label, 180)
        for r in range(8):
            add_label(b, str(r + 1), (-4.33, -0.04, 3.5 - r), 0.085, label)
            add_label(b, str(r + 1), (4.33, -0.04, 3.5 - r), 0.085, label, 180)
        # bandejas laterais para peças fora do tabuleiro
        for x in (-6.0, 6.0):
            b.cube((x, TABLE_TOP + 0.04, 0), (2.3, 0.08, 8.3), TRAY, 0.8)
            b.cube((x, TABLE_TOP + 0.05, 0), (2.05, 0.08, 8.05), (0.16, 0.30, 0.20), 0.9)
        return as_static(b)

    # ------------------------------------------------------------ estado atual
    def layout(self):
        """Dicionário célula -> peça para desenhar (tabuleiro + bandejas)."""
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
        pos = cr.Position(board, turn, cr.infer_castling(board), None, 0, 1)
        return pos

    # ------------------------------------------------------------ comandos
    def toggle_mode(self):
        if self.mode == "jogo":
            self.mode = "livre"
            self.free = self.layout()
            self.selected = None
            self.pending_promo = None
            self.toast("Modo livre: mova qualquer peça para qualquer lugar")
        else:
            self._return_held()
            self.mode = "jogo"
            self.toast("Modo jogo: regras oficiais (a partida anterior continua)")

    def start_from_free(self, turn):
        self._return_held()
        pos = self.free_position(turn)
        err = cr.validate_position(pos)
        if err:
            self.toast("Posição inválida: " + err)
            return
        self.game = cr.ChessGame(pos)
        self.counted = None
        self.mode = "jogo"
        self.anims.clear()
        self.toast(f"Partida iniciada desta posição - vez das {COLOR_PT[turn]}")

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
            self.toast("Nova partida")

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
        """Mantém o placar de partidas em dia com o resultado atual."""
        res = self.game.result
        if res == self.counted:
            return
        if self.counted:
            self._apply_result(self.counted, -1)
        if res:
            self._apply_result(res, +1)
        self.counted = res

    def _apply_result(self, res, sign):
        if res == "1-0":
            self.tally["w"] += sign
        elif res == "0-1":
            self.tally["b"] += sign
        else:
            self.tally["w"] += 0.5 * sign
            self.tally["b"] += 0.5 * sign

    def _return_held(self):
        if self.held:
            piece, origin = self.held
            target = origin if origin and origin not in self.free else self._free_tray_cell(piece[0])
            if target:
                self.free[target] = piece
            self.held = None

    def _free_tray_cell(self, color):
        files = (-2, -3) if color == "b" else (9, 10)
        for f in files:
            for r in range(8):
                if (f, r) not in self.free:
                    return (f, r)
        for f in TRAY_FILES:
            for r in range(8):
                if (f, r) not in self.free:
                    return (f, r)
        return None

    # ------------------------------------------------------------ entrada
    def set_hover(self, cell):
        self.hover = cell

    def pick(self, camera, mx, my, w, h):
        p = camera.pick_plane(mx, my, w, h, 0.0)
        c = world_to_cell(p)
        if c and 0 <= c[0] < 8:
            return c
        p = camera.pick_plane(mx, my, w, h, TRAY_Y)
        c = world_to_cell(p)
        if c and c[0] in TRAY_FILES:
            return c
        return None

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
            piece, _origin = self.held
            self.free[cell] = piece
            self.anims[cell] = (None, self.time)
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
        if self.selected is not None:
            frm = self.selected
            if any(m.to == s for m in g.moves_from(frm)):
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
            self.toast("Essa peça não tem lances legais")
        else:
            self.selected = None

    def _play(self, move):
        g = self.game
        before_caps = {c: len(g.captured_by(c)) for c in "wb"}
        mover = g.pos.turn
        cap_sq = move.to
        if move.en_passant:
            cap_sq = cr.sq(cr.file_of(move.to), cr.rank_of(move.frm))
        captured = g.push(move)
        self.selected = None
        self.anims.clear()
        to_cell = (cr.file_of(move.to), cr.rank_of(move.to))
        self.anims[to_cell] = ((cr.file_of(move.frm), cr.rank_of(move.frm)), self.time)
        if move.castle:
            rank = cr.rank_of(move.frm)
            if cr.file_of(move.to) == 6:
                self.anims[(5, rank)] = ((7, rank), self.time)
            else:
                self.anims[(3, rank)] = ((0, rank), self.time)
        if captured:
            k = before_caps[mover]
            files = (9, 10) if mover == "w" else (-2, -3)
            if k < 16:
                self.anims[(files[k // 8], k % 8)] = ((cr.file_of(cap_sq), cr.rank_of(cap_sq)), self.time)
        self._sync_tally()
        if g.result:
            self.toast(self.result_text())
        elif g.pos.in_check():
            self.toast("Xeque!")

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
                self.toast(f"{COLOR_PT[loser]} desistiram. " + self.result_text())
            return True
        if self.mode == "livre":
            kinds = {pygame.K_1: "P", pygame.K_2: "N", pygame.K_3: "B", pygame.K_4: "R",
                     pygame.K_5: "Q", pygame.K_6: "K"}
            if key in kinds:
                self._return_held()
                color = "b" if shift else "w"
                self.held = ((color, kinds[key]), None)
                self.toast(f"Nova peça na mão: {cr.PIECE_NAMES_PT[kinds[key]]} ({COLOR_PT[color]})")
                return True
            if key == pygame.K_c and self.held:
                (color, kind), origin = self.held
                self.held = ((cr.other(color), kind), origin)
                return True
            if key in (pygame.K_DELETE, pygame.K_BACKSPACE) and self.held:
                self.held = None
                self.toast("Peça removida")
                return True
            if key == pygame.K_x:
                self._return_held()
                self.free = {}
                pieces = sorted(standard_free_layout().values(), key=lambda p: -cr.PIECE_VALUES[p[1]])
                for p in pieces:
                    cell = self._free_tray_cell(p[0])
                    if cell:
                        self.free[cell] = p
                self.toast("Tabuleiro vazio: peças nas bandejas")
                return True
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.start_from_free("b" if shift else "w")
                return True
        return False

    # ------------------------------------------------------------ desenho
    def update(self, dt):
        self.time += dt
        done = [c for c, (_s, t0) in self.anims.items() if self.time - t0 > ANIM_TIME]
        for c in done:
            del self.anims[c]

    def build(self, batch: InstanceBatch):
        batch.add_array(self.static)
        g = self.game
        last = g.last_move() if self.mode == "jogo" else None
        check_sq = g.pos.king_square(g.pos.turn) if self.mode == "jogo" and g.pos.in_check() else None
        targets = {}
        if self.mode == "jogo" and self.selected is not None:
            for m in g.moves_from(self.selected):
                targets[m.to] = m
        hover_sq = cr.sq(*self.hover) if self.hover and 0 <= self.hover[0] < 8 else None

        # casas do tabuleiro (cores dinâmicas para destaques)
        sq_arr = np.empty((64, 10), dtype=np.float32)
        for s in range(64):
            f, r = cr.file_of(s), cr.rank_of(s)
            col = LIGHT_SQ if (f + r) % 2 else DARK_SQ
            if last and s in (last.frm, last.to):
                col = mix(col, LAST, 0.45)
            if s == self.selected:
                col = mix(col, SEL, 0.65)
            if s == check_sq:
                col = mix(col, CHECK, 0.7)
            if s == hover_sq:
                col = mix(col, HOVER, 0.18)
            sq_arr[s] = (f - 3.5, -0.06, 3.5 - r, 1.0, 0.12, 1.0, *col, 0.9)
        batch.add_array(sq_arr)

        # marcadores de lances possíveis
        for s, m in targets.items():
            x, z = cr.file_of(s) - 3.5, 3.5 - cr.rank_of(s)
            if g.pos.board[s] or m.en_passant:
                for dx in (-0.4, 0.4):
                    for dz in (-0.4, 0.4):
                        batch.cube((x + dx, 0.03, z + dz), (0.14, 0.06, 0.14), CAPTURE_MARK, 2.0)
            else:
                pulse = 0.16 + 0.03 * math.sin(self.time * 6)
                batch.cube((x, 0.03, z), (pulse, 0.06, pulse), MOVE_DOT, 2.0)

        # marcador de hover nas bandejas / modo livre
        if self.hover and (self.mode == "livre" or self.hover[0] not in range(8)):
            c = cell_center(self.hover)
            col = SEL if self.held else HOVER
            for dx, dz, sx, sz in ((0, -0.48, 1.0, 0.05), (0, 0.48, 1.0, 0.05),
                                   (-0.48, 0, 0.05, 1.0), (0.48, 0, 0.05, 1.0)):
                batch.cube((c[0] + dx, c[1] + 0.02, c[2] + dz), (sx, 0.04, sz), col, 2.0)

        # peças
        for cell, piece in self.layout().items():
            pos = cell_center(cell)
            if cell in self.anims:
                src, t0 = self.anims[cell]
                t = smoothstep((self.time - t0) / ANIM_TIME)
                if src is None:   # peça largada no modo livre: pequena queda
                    pos = pos + np.array([0, (1 - t) * 0.5, 0], dtype=np.float32)
                else:
                    a = cell_center(src)
                    pos = a + (pos - a) * t
                    pos[1] += arc(t, 0.9)
            mpos, mcol = self.models[piece]
            sel = self.mode == "jogo" and self.selected is not None and cell == (
                cr.file_of(self.selected), cr.rank_of(self.selected))
            if sel:
                pos = pos + np.array([0, 0.12 + 0.04 * math.sin(self.time * 5), 0], dtype=np.float32)
            batch.model(mpos, mcol, pos, voxel=VOX)

        # peça na mão (modo livre)
        if self.held:
            piece, _ = self.held
            target = self.hover
            if target:
                pos = cell_center(target) + np.array([0, 0.7 + 0.08 * math.sin(self.time * 4), 0],
                                                     dtype=np.float32)
                mpos, mcol = self.models[piece]
                batch.model(mpos, mcol, pos, voxel=VOX)
                # "sombra" de destino
                c = cell_center(target)
                batch.cube((c[0], c[1] + 0.015, c[2]), (0.8, 0.03, 0.8), (0.95, 0.85, 0.35), 2.0)

    # ------------------------------------------------------------ HUD
    def result_text(self):
        g = self.game
        if not g.result:
            return ""
        if g.result == "1-0":
            return f"{g.reason}! Brancas vencem (1-0)"
        if g.result == "0-1":
            return f"{g.reason}! Pretas vencem (0-1)"
        return f"Empate: {g.reason} (½-½)"

    def hud(self):
        g = self.game
        lines = []
        mode = "MODO JOGO" if self.mode == "jogo" else "MODO LIVRE"
        title = f"XADREZ  ·  {mode}"
        if self.mode == "jogo":
            if g.result:
                lines.append((self.result_text(), (255, 220, 120)))
            else:
                turn = COLOR_PT[g.pos.turn]
                extra = "  —  XEQUE!" if g.pos.in_check() else ""
                lines.append((f"Vez das {turn}{extra}", (255, 255, 255)))
            sc = g.score()
            diff = sc["diff"]
            adv = "igual" if diff == 0 else (f"Brancas +{diff}" if diff > 0 else f"Pretas +{-diff}")
            lines.append((f"Material  Brancas {sc['w']}  ·  Pretas {sc['b']}   ({adv})", (210, 230, 255)))
            cw = sum(cr.PIECE_VALUES[p[1]] for p in g.captured_by("w"))
            cb = sum(cr.PIECE_VALUES[p[1]] for p in g.captured_by("b"))
            lines.append((f"Capturas  Brancas {cw} pts  ·  Pretas {cb} pts", (200, 200, 220)))
            lines.append((f"Placar de partidas  Brancas {self.tally['w']:g}  x  {self.tally['b']:g} Pretas",
                          (255, 200, 140)))
            ml = g.move_list()
            if ml:
                lines.append(("Lances: " + "  ".join(ml[-3:]), (180, 180, 200)))
            hints = ["Clique: selecionar/mover", "G: desistir", "Z: desfazer", "R: nova partida",
                     "M: modo livre"]
            if self.pending_promo:
                lines.append(("PROMOÇÃO: 1 Dama  2 Torre  3 Bispo  4 Cavalo  (Esc cancela)", (255, 240, 120)))
        else:
            pos = self.free_position()
            w, b = pos.material("w"), pos.material("b")
            d = w - b
            adv = "igual" if d == 0 else (f"Brancas +{d}" if d > 0 else f"Pretas +{-d}")
            lines.append((f"Material no tabuleiro  Brancas {w}  ·  Pretas {b}   ({adv})", (210, 230, 255)))
            if self.held:
                p = self.held[0]
                lines.append((f"Na mão: {cr.PIECE_NAMES_PT[p[1]]} ({COLOR_PT[p[0]]})", (255, 230, 150)))
            err = cr.validate_position(pos)
            if err:
                lines.append(("Para jogar: " + err, (230, 170, 170)))
            else:
                lines.append(("Posição válida - Enter inicia partida (Shift+Enter: pretas começam)",
                              (170, 230, 170)))
            hints = ["Clique: pegar/soltar", "1-6: nova peça (Shift = preta)", "C: trocar cor",
                     "Del: descartar", "X: esvaziar", "R: posição inicial", "M: modo jogo"]
        return title, lines, hints
