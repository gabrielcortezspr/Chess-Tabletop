"""Cena do Go: goban voxel, pedras, contagem automática, modos Jogo e Livre."""
from __future__ import annotations

import math

import numpy as np
import pygame

from . import go_rules as gr
from .renderer import InstanceBatch
from .scene_common import TABLE_TOP, add_label, as_static, build_room
from .voxels import go_bowl, go_stone

BOARD_WOOD = (0.86, 0.64, 0.36)
LINE = (0.16, 0.10, 0.06)
TERR = {gr.BLACK: (0.10, 0.10, 0.14), gr.WHITE: (0.97, 0.97, 0.95)}
SIZES = (9, 13, 19)
KOMIS = (0.5, 5.5, 6.5, 7.5)
DROP_TIME = 0.25
SPAN = 9.0


class GoScene:
    name = "Go"
    focus_radius = 6.5

    def __init__(self, size=19):
        self.game = gr.GoGame(size)
        self.mode = "jogo"
        self.free_color = gr.BLACK
        self.hover = None
        self.time = 0.0
        self.drop = None              # (x, y, t0) animação da última pedra
        self.show_terr = False
        self.tally = {gr.BLACK: 0, gr.WHITE: 0}
        self.counted = None
        self.message = ("", 0.0)
        self._est_key = None
        self._est = None
        self._legal_key = None
        self._legal = False
        self._setup_geometry()

    # ------------------------------------------------------------ geometria
    def _setup_geometry(self):
        n = self.game.size
        self.s = SPAN / (n - 1)
        self.vox = self.s * 0.092
        self.stone = {gr.BLACK: go_stone("b", self.vox), gr.WHITE: go_stone("w", self.vox)}
        self.static = self._build_static()

    def point_world(self, x, y):
        n = self.game.size
        return np.array([(x - (n - 1) / 2) * self.s, 0.0, ((n - 1) / 2 - y) * self.s], dtype=np.float32)

    def world_to_point(self, p):
        if p is None:
            return None
        n = self.game.size
        x = round(p[0] / self.s + (n - 1) / 2)
        y = round((n - 1) / 2 - p[2] / self.s)
        if 0 <= x < n and 0 <= y < n:
            return (x, y)
        return None

    def _build_static(self):
        b = InstanceBatch()
        build_room(b)
        n, s = self.game.size, self.s
        half = SPAN / 2 + s * 0.5 + 0.45
        # bloco do goban (com pés curtos)
        b.cube((0, -0.24, 0), (2 * half, 0.48, 2 * half), BOARD_WOOD, 1.0)
        b.cube((0, -0.49, 0), (2 * half - 0.3, 0.02, 2 * half - 0.3), (0.5, 0.33, 0.18), 0.5)
        # linhas
        lw = 0.035
        for i in range(n):
            p = self.point_world(i, 0)
            b.cube((p[0], 0.005, 0), (lw, 0.012, SPAN + lw), LINE, 0.0)
            q = self.point_world(0, i)
            b.cube((0, 0.005, q[2]), (SPAN + lw, 0.012, lw), LINE, 0.0)
        # hoshi
        for x, y in self.star_points():
            p = self.point_world(x, y)
            r = min(0.14, s * 0.22)
            b.cube((p[0], 0.008, p[2]), (r, 0.014, r), LINE, 0.0)
        # coordenadas
        px = min(0.085, s * 0.13)
        for i in range(n):
            letter = gr.LETTERS[i]
            p = self.point_world(i, 0)
            add_label(b, letter, (p[0], 0.0, SPAN / 2 + s * 0.25 + 0.25), px, LINE, height=0.01)
            p = self.point_world(0, i)
            add_label(b, str(i + 1), (-SPAN / 2 - s * 0.25 - 0.3, 0.0, p[2]), px, LINE, height=0.01)
        # potes de pedras
        bpos, bcol = go_bowl(0.09)
        for color, x in ((gr.BLACK, half + 1.6), (gr.WHITE, -half - 1.6)):
            off = np.array([x, TABLE_TOP, 1.5], dtype=np.float32)
            b.model(bpos, bcol, off, voxel=0.09, mat=0.6)
            spos, scol = go_stone("b" if color == gr.BLACK else "w", 0.04)
            rng = np.random.default_rng(color)
            offs = []
            for k in range(14):
                a, r = rng.random() * 6.28, rng.random() * 0.62
                offs.append((x + math.cos(a) * r, TABLE_TOP + 0.12 + (k // 6) * 0.12, 1.5 + math.sin(a) * r))
            b.models_many(spos, scol, offs, voxel=0.04)
            # tampa ao lado (onde ficam os prisioneiros)
            b.cube((x, TABLE_TOP + 0.05, -1.4), (1.6, 0.1, 1.6), (0.48, 0.28, 0.15), 0.8)
        return as_static(b)

    def star_points(self):
        n = self.game.size
        if n == 19:
            c = (3, 9, 15)
        elif n == 13:
            c = (3, 6, 9)
        else:
            return [(2, 2), (6, 2), (4, 4), (2, 6), (6, 6)]
        return [(x, y) for x in c for y in c]

    def lid_offsets(self, color, count):
        half = SPAN / 2 + self.s * 0.5 + 0.45
        x0 = half + 1.6 if color == gr.BLACK else -half - 1.6
        offs = []
        for k in range(min(count, 60)):
            layer, i = divmod(k, 16)
            gx, gz = i % 4, i // 4
            offs.append((x0 - 0.54 + gx * 0.36, TABLE_TOP + 0.1 + layer * 0.17, -1.4 - 0.54 + gz * 0.36))
        return offs

    # ------------------------------------------------------------ estado
    def toast(self, text):
        self.message = (text, self.time)

    def estimate(self):
        key = (self.game.board.key(), self.game.komi)
        if key != self._est_key:
            self._est_key = key
            self._est = self.game.estimate()
        return self._est

    def hover_legal(self):
        if not self.hover:
            return False
        key = (self.hover, self.game.board.key(), self.game.turn, self.game.phase)
        if key != self._legal_key:
            self._legal_key = key
            self._legal = self.game.is_legal(*self.hover)
        return self._legal

    def _sync_tally(self):
        f = self.game.final if self.game.phase == "over" else None
        winner = f["winner"] if f else None
        key = (id(self.game.final), winner) if f else None
        if key == self.counted:
            return
        if self.counted and self.counted[1]:
            self.tally[self.counted[1]] -= 1
        if f and winner:
            self.tally[winner] += 1
        self.counted = key

    # ------------------------------------------------------------ comandos
    def toggle_mode(self):
        if self.mode == "jogo":
            self.mode = "livre"
            self.toast("Modo livre: coloque/remova pedras à vontade (sem regras)")
        else:
            self.mode = "jogo"
            self.toast("Modo jogo: regras oficiais")

    def reset(self):
        if self.mode == "livre":
            self.game.board = gr.GoBoard(self.game.size)
            self.toast("Goban limpo")
        else:
            self.game.reset()
            self.counted = None
            self.toast(f"Nova partida {self.game.size}x{self.game.size}")
        self.drop = None

    def undo(self):
        if self.mode == "livre":
            return
        if self.game.undo():
            self._sync_tally()
            self.drop = None
            self.toast("Jogada desfeita")

    def set_size(self, n):
        self.game.size = n
        self.game.reset(n)
        self.counted = None
        self.drop = None
        self._setup_geometry()
        self.toast(f"Goban {n}x{n}")

    # ------------------------------------------------------------ entrada
    def set_hover(self, cell):
        self.hover = cell

    def pick(self, camera, mx, my, w, h):
        return self.world_to_point(camera.pick_plane(mx, my, w, h, 0.0))

    def click(self, pt, shift=False):
        if pt is None:
            return
        g = self.game
        x, y = pt
        if self.mode == "livre":
            if g.board.get(x, y) != gr.EMPTY:
                g.board.set(x, y, gr.EMPTY)
            else:
                color = gr.opp(self.free_color) if shift else self.free_color
                g.board.set(x, y, color)
                self.drop = (x, y, self.time)
            return
        if g.phase == "scoring":
            g.toggle_dead(x, y)
            return
        if g.phase != "play":
            return
        ok, msg, captured = g.try_play(x, y)
        if not ok:
            self.toast(msg)
            return
        self.drop = (x, y, self.time)
        if captured:
            self.toast(f"{len(captured)} pedra(s) capturada(s)!")

    def key(self, key, mod):
        g = self.game
        shift = bool(mod & pygame.KMOD_SHIFT)
        if key == pygame.K_b:
            self.set_size(SIZES[(SIZES.index(g.size) + 1) % len(SIZES)] if g.size in SIZES else 19)
            return True
        if key == pygame.K_k:
            i = KOMIS.index(g.komi) if g.komi in KOMIS else 2
            g.komi = KOMIS[(i + 1) % len(KOMIS)]
            self._est_key = None
            if g.phase == "over" and g.final and g.resigned is None:
                g.phase = "scoring"
                g.finish_scoring()
                self._sync_tally()
            self.toast(f"Komi: {g.komi}")
            return True
        if key == pygame.K_t:
            self.show_terr = not self.show_terr
            self.toast("Território: " + ("visível" if self.show_terr else "oculto"))
            return True
        if self.mode == "livre":
            if key == pygame.K_c:
                self.free_color = gr.opp(self.free_color)
                return True
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                board = g.board.copy()
                turn = gr.opp(self.free_color) if shift else self.free_color
                # remove grupos sem liberdades antes de começar
                for _c, stones, libs in board.all_groups():
                    if not libs:
                        for sx, sy in stones:
                            board.set(sx, sy, gr.EMPTY)
                g.reset(board=board, turn=turn)
                self.counted = None
                self.mode = "jogo"
                self.toast(f"Partida iniciada desta posição - vez das {gr.COLOR_NAME[turn]}")
                return True
            return False
        if key == pygame.K_p and g.phase == "play":
            g.pass_turn()
            if g.phase == "scoring":
                self.toast("Dois passes: contagem! Clique nos grupos mortos e Enter para confirmar")
            else:
                self.toast(f"{gr.COLOR_NAME[gr.opp(g.turn)]} passaram")
            return True
        if key == pygame.K_g and g.phase == "play":
            g.resign()
            self._sync_tally()
            self.toast(g.final["text"])
            return True
        if g.phase == "scoring":
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                g.finish_scoring()
                self._sync_tally()
                self.toast(g.final["text"])
                return True
            if key == pygame.K_v:
                g.resume_play()
                self.toast("Partida retomada")
                return True
            if key == pygame.K_u:
                g.dead = gr.estimate_dead(g.board)
                self.toast("Mortas sugeridas automaticamente")
                return True
        return False

    # ------------------------------------------------------------ desenho
    def update(self, dt):
        self.time += dt

    def build(self, batch: InstanceBatch):
        batch.add_array(self.static)
        g = self.game
        n = g.size
        dead = g.dead if g.phase in ("scoring", "over") else set()
        groups = {gr.BLACK: [], gr.WHITE: []}
        dead_list = []
        drop_off = None
        for y in range(n):
            for x in range(n):
                c = g.board.get(x, y)
                if c == gr.EMPTY:
                    continue
                p = self.point_world(x, y)
                if self.drop and (x, y) == self.drop[:2]:
                    t = min(1.0, (self.time - self.drop[2]) / DROP_TIME)
                    if t < 1.0:
                        drop_off = (c, p + np.array([0, (1 - t) ** 2 * 1.2, 0], dtype=np.float32))
                        continue
                if (x, y) in dead:
                    dead_list.append((c, p))
                else:
                    groups[c].append(p)
        for c, offs in groups.items():
            pos, col = self.stone[c]
            batch.models_many(pos, col, offs, voxel=self.vox)
        if drop_off:
            pos, col = self.stone[drop_off[0]]
            batch.model(pos, col, drop_off[1], voxel=self.vox)
        for c, p in dead_list:
            pos, col = self.stone[c]
            batch.model(pos, col, p, voxel=self.vox, tint=(0.8, 0.3, 0.3))

        # prisioneiros nas tampas
        for color in (gr.BLACK, gr.WHITE):
            pris = g.captures[color]
            if pris:
                # prisioneiros de `color` são pedras da cor oposta
                pc = gr.opp(color)
                spos, scol = go_stone("b" if pc == gr.BLACK else "w", 0.04)
                batch.models_many(spos, scol, self.lid_offsets(color, pris), voxel=0.04)

        # território
        terr = None
        if g.phase in ("scoring", "over"):
            terr = g.area_score()["terr_map"]
            for (x, y) in dead:
                terr[(x, y)] = gr.opp(g.board.get(x, y))
        elif self.show_terr:
            terr = self.estimate()["terr_map"]
        if terr:
            sz = self.s * 0.32
            for (x, y), owner in terr.items():
                p = self.point_world(x, y)
                h = 0.03 if g.board.get(x, y) == gr.EMPTY else self.vox * 5.3
                batch.cube((p[0], h, p[2]), (sz, 0.04, sz), TERR[owner], 2.0)

        # última jogada
        if self.mode == "jogo" and isinstance(g.last_move, tuple):
            x, y = g.last_move
            if g.board.get(x, y) != gr.EMPTY and not (drop_off and self.drop[:2] == (x, y)):
                p = self.point_world(x, y)
                sz = self.s * 0.22
                batch.cube((p[0], self.vox * 5.2, p[2]), (sz, 0.03, sz), (0.95, 0.30, 0.25), 2.0)

        # cursor / pedra fantasma
        if self.hover:
            x, y = self.hover
            p = self.point_world(x, y)
            if self.mode == "livre":
                col = (0.95, 0.85, 0.35) if g.board.get(x, y) == gr.EMPTY else (0.95, 0.35, 0.3)
                self._ring(batch, p, col)
            elif g.phase == "play":
                if self.hover_legal():
                    pos, ccol = self.stone[g.turn]
                    bob = 0.25 + 0.05 * math.sin(self.time * 5)
                    batch.model(pos, ccol, p + np.array([0, bob, 0], dtype=np.float32), voxel=self.vox,
                                scale=0.8)
                    self._ring(batch, p, (0.95, 0.85, 0.35))
                else:
                    self._ring(batch, p, (0.95, 0.35, 0.3))
            elif g.phase == "scoring" and g.board.get(x, y) != gr.EMPTY:
                self._ring(batch, p, (0.95, 0.35, 0.3))

    def _ring(self, batch, p, col):
        r = self.s * 0.5
        t = 0.03
        for dx, dz, sx, sz in ((0, -r, 2 * r, t), (0, r, 2 * r, t), (-r, 0, t, 2 * r), (r, 0, t, 2 * r)):
            batch.cube((p[0] + dx, 0.02, p[2] + dz), (sx, 0.03, sz), col, 2.0)

    # ------------------------------------------------------------ HUD
    def hud(self):
        g = self.game
        mode = "MODO JOGO" if self.mode == "jogo" else "MODO LIVRE"
        title = f"GO {g.size}x{g.size}  ·  {mode}"
        lines = []
        cap = f"Capturas  Pretas {g.captures[gr.BLACK]}  ·  Brancas {g.captures[gr.WHITE]}"
        if self.mode == "livre":
            est = self.estimate()
            lines.append((f"Cor ao clicar: {gr.COLOR_NAME[self.free_color]} (C troca, Shift inverte)",
                          (255, 230, 150)))
            lines.append((f"Estimativa (área)  Pretas {est['black']:g}  ·  Brancas {est['white']:g}"
                          f"  (komi {g.komi})", (210, 230, 255)))
            hints = ["Clique: colocar/remover", "C: cor", "Enter: jogar desta posição", "R: limpar",
                     "B: tamanho", "T: território", "M: modo jogo"]
            return title, lines, hints
        if g.phase == "play":
            last = ""
            if g.last_move == "pass":
                last = "  (adversário passou)"
            elif isinstance(g.last_move, tuple):
                last = f"  (último: {gr.coord_name(*g.last_move)})"
            lines.append((f"Vez das {gr.COLOR_NAME[g.turn]}  ·  jogada {g.move_number + 1}{last}",
                          (255, 255, 255)))
            lines.append((cap, (200, 200, 220)))
            est = self.estimate()
            diff = est["black"] - est["white"]
            lead = f"Pretas +{diff:g}" if diff > 0 else (f"Brancas +{-diff:g}" if diff < 0 else "empate")
            lines.append((f"Estimativa  Pretas {est['black']:g}  ·  Brancas {est['white']:g}  ({lead}, komi {g.komi})",
                          (210, 230, 255)))
            hints = ["Clique: jogar", "P: passar", "G: desistir", "Z: desfazer", "T: território",
                     "K: komi", "B: tamanho", "R: nova", "M: modo livre"]
        elif g.phase == "scoring":
            s = g.area_score()
            lines.append(("CONTAGEM: clique nos grupos mortos (vermelhos) para alternar", (255, 230, 120)))
            lines.append((f"Área (chinesa)  Pretas {s['black']:g}  ·  Brancas {s['white']:g}  (komi {g.komi})",
                          (210, 230, 255)))
            lines.append((f"Território (japonesa)  Pretas {s['jp_black']:g}  ·  Brancas {s['jp_white']:g}",
                          (190, 200, 230)))
            hints = ["Clique: marcar morta", "Enter: confirmar", "U: sugestão automática",
                     "V: voltar a jogar", "Z: desfazer"]
        else:
            f = g.final
            lines.append((f["text"], (255, 220, 120)))
            if f.get("margin") is not None:
                lines.append((f"Área  Pretas {f['black']:g}  ·  Brancas {f['white']:g}  (komi {g.komi})",
                              (210, 230, 255)))
                lines.append((f"Território  Pretas {f['jp_black']:g}  ·  Brancas {f['jp_white']:g}",
                              (190, 200, 230)))
            hints = ["R: nova partida", "Z: desfazer", "K: komi", "B: tamanho", "M: modo livre"]
        lines.append((f"Placar de partidas  Pretas {self.tally[gr.BLACK]}  x  {self.tally[gr.WHITE]} Brancas",
                      (255, 200, 140)))
        return title, lines, hints
