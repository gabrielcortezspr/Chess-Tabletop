"""Mesa de Go em pixel art: modos Jogo e Livre, contagem automática."""
from __future__ import annotations

import math

import pygame

from . import go_rules as gr
from .fx import ease_out_back
from .pixelart import OUTLINE, draw_tiny, stone_sprite, tiny_width
from .scene_base import SceneBase
from .storage import copy_text, load_positions, paste_text, save_position

CELL = {9: 18, 13: 12, 19: 8}
MARGIN = {9: 14, 13: 12, 19: 11}
SIZES = (9, 13, 19)
KOMIS = (0.5, 5.5, 6.5, 7.5)
WOOD = (222, 168, 96)
WOOD_DARK = (196, 140, 76)
LINE = (70, 40, 26)
DROP_TIME = 0.28
NAME = gr.COLOR_NAME


class GoScene(SceneBase):
    name = "Go"
    theme = ((0.12, 0.62, 0.52), (0.93, 0.66, 0.18), (0.07, 0.11, 0.13))

    def __init__(self, size=19):
        super().__init__()
        self.game = gr.GoGame(size)
        self.free_color = gr.BLACK
        self.free_board = gr.GoBoard(size)
        self.saved_index = -1
        self.flipped = False
        self.drop = None
        self.show_terr = False
        self.tally = {gr.BLACK: 0, gr.WHITE: 0}
        self.counted = None
        self._est_key = self._est = None
        self._legal_key = None
        self._legal = False
        self._setup()

    # ------------------------------------------------------------ geometria
    def _setup(self):
        n = self.game.size
        self.cell = CELL.get(n, 8)
        self.margin = MARGIN.get(n, 11)
        size = self.margin * 2 + self.cell * (n - 1) + 1
        self.tex_size = (size, size)
        d = self.cell - 1 if self.cell > 8 else self.cell
        self.stones = {gr.BLACK: stone_sprite(d, "b"), gr.WHITE: stone_sprite(d, "w")}
        self.small = {gr.BLACK: stone_sprite(max(5, d // 2), "b"), gr.WHITE: stone_sprite(max(5, d // 2), "w")}
        self._static = {}

    def _disp(self, x, y):
        n = self.game.size
        return (n - 1 - x, n - 1 - y) if self.flipped else (x, y)

    def point_xy(self, x, y):
        dx, dy = self._disp(x, y)
        n = self.game.size
        return self.margin + dx * self.cell, self.margin + (n - 1 - dy) * self.cell

    def pick_tex(self, px, py):
        n = self.game.size
        dx = round((px - self.margin) / self.cell)
        dy = n - 1 - round((py - self.margin) / self.cell)
        if 0 <= dx < n and 0 <= dy < n:
            return self._disp(dx, dy)
        return None

    def cell_center(self, pt):
        return self.point_xy(*pt)

    def flip(self):
        self.flipped = not self.flipped

    def _static_surface(self):
        if self.flipped in self._static:
            return self._static[self.flipped]
        w, h = self.tex_size
        n = self.game.size
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill(WOOD)
        pygame.draw.rect(s, (240, 194, 124), (0, 0, w, 1))
        pygame.draw.rect(s, (240, 194, 124), (0, 0, 1, h))
        pygame.draw.rect(s, WOOD_DARK, (0, h - 2, w, 2))
        pygame.draw.rect(s, WOOD_DARK, (w - 2, 0, 2, h))
        for k in range(0, h, 5):   # veios
            x0 = (k * 37) % w
            pygame.draw.line(s, WOOD_DARK, (x0, k), (min(w - 3, x0 + 10 + k % 13), k))
        for i in range(n):
            x0, y0 = self.point_xy(i, 0)
            x1, y1 = self.point_xy(i, n - 1)
            pygame.draw.line(s, LINE, (x0, y0), (x1, y1))
            x0, y0 = self.point_xy(0, i)
            x1, y1 = self.point_xy(n - 1, i)
            pygame.draw.line(s, LINE, (x0, y0), (x1, y1))
        for x, y in self.star_points():
            px, py = self.point_xy(x, y)
            pygame.draw.rect(s, LINE, (px - 1, py - 1, 3, 3))
        for i in range(n):
            px, py = self.point_xy(i, 0)
            ch = gr.LETTERS[i]
            draw_tiny(s, ch, px - 1, h - self.margin + 4 if self.margin > 10 else h - 6, LINE)
            px, py = self.point_xy(0, i)
            label = str(i + 1)
            draw_tiny(s, label, max(1, px - tiny_width(label) - 3), py - 2, LINE)
        self._static[self.flipped] = s
        return s

    def star_points(self):
        n = self.game.size
        c = {19: (3, 9, 15), 13: (3, 6, 9)}.get(n)
        if not c:
            return [(2, 2), (6, 2), (4, 4), (2, 6), (6, 6)]
        return [(x, y) for x in c for y in c]

    # ------------------------------------------------------------ estado
    def board(self):
        """Tabuleiro exibido: o da partida ou o de criação livre."""
        return self.free_board if self.mode == "livre" else self.game.board

    def estimate(self):
        b = self.board()
        komi = self.game.komi + (self.game.handicap if self.mode == "jogo" else 0)
        key = (b.key(), komi)
        if key != self._est_key:
            self._est_key = key
            self._est = gr.estimate_board(b, komi)
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
        key = (id(f), f["winner"]) if f else None
        if key == self.counted:
            return
        if self.counted and self.counted[1]:
            self.tally[self.counted[1]] -= 1
        if f and f["winner"]:
            self.tally[f["winner"]] += 1
        self.counted = key

    # ------------------------------------------------------------ comandos
    def toggle_mode(self):
        if self.mode == "jogo":
            self.mode = "livre"
            self.free_board = self.game.board.copy()   # cópia: a partida fica intacta
            self.toast("Modo livre: monte qualquer posição")
        else:
            self.mode = "jogo"
            self.toast("Modo jogo: a partida continua de onde parou")

    def reset(self, standard=False):
        if self.mode == "livre":
            self.free_board = gr.GoBoard(self.game.size)
            self.toast("Goban limpo")
        else:
            board, turn, ha = self.game.start
            if standard or not any(board.get(x, y) for y in range(board.size) for x in range(board.size)):
                self.game.reset()
                self.emit("banner", "NOVA PARTIDA", (255, 214, 90))
            else:
                self.game.reset(board=board, turn=turn, handicap=ha)
                self.emit("banner", "DE NOVO!", (255, 214, 90))
                self.toast("Recomeçou da posição inicial (Shift+R: goban vazio)")
            self.counted = None
        self.drop = None
        self.emit("sheen")

    def undo(self):
        if self.mode == "livre":
            return
        if self.game.undo():
            self._sync_tally()
            self.drop = None
            self.toast("Jogada desfeita (Y refaz)")

    def redo(self):
        if self.mode == "livre":
            return
        action = self.game.redo()
        if action and action[0] == "play":
            self.drop = (action[1], action[2], self.time)
        elif action is None:
            self.toast("Nada para refazer")
        if self.game.phase == "scoring":
            self.emit("banner", "CONTAGEM!", (255, 214, 90))

    def start_from_free(self, turn):
        board = self.free_board.copy()
        removed = 0
        for _c, stones, libs in board.all_groups():
            if not libs:
                removed += len(stones)
                for sx, sy in stones:
                    board.set(sx, sy, gr.EMPTY)
        komi = self.game.komi
        self.game.reset(board=board, turn=turn)
        self.game.komi = komi
        self.counted = None
        self.mode = "jogo"
        self.emit("banner", "VALENDO!", (255, 214, 90))
        extra = f" ({removed} pedra(s) sem liberdade removida(s))" if removed else ""
        self.toast(f"Vez das {NAME[turn]}{extra}")

    # ------------------------------------------------------------ treino
    def export_text(self):
        if self.mode == "livre":
            tmp = gr.GoGame(self.game.size, self.game.komi)
            tmp.reset(board=self.free_board, turn=self.free_color)
            return gr.to_sgf(tmp)
        return gr.to_sgf(self.game)

    def load_text(self, text):
        try:
            game = gr.from_sgf(text)
        except ValueError as e:
            self.toast(str(e))
            self.emit("shake", 3)
            return False
        n_moves = len(game.actions)
        game.rewind()
        self.game = game
        self._setup()
        self.counted = None
        self.drop = None
        self.mode = "jogo"
        self.emit("sheen")
        self.emit("banner", "SGF CARREGADO", (255, 214, 90))
        self.toast(f"{n_moves} jogada(s): Y avança, Z volta" if n_moves else "Posição carregada")
        return True

    def training_key(self, key, mod):
        if not mod & pygame.KMOD_CTRL:
            return False
        if key == pygame.K_c:
            ok = copy_text(self.export_text())
            self.toast("SGF copiado" if ok else "SGF salvo em posicoes/copiado.txt")
        elif key == pygame.K_v:
            text = paste_text()
            if not text:
                self.toast("Área de transferência vazia (ou use posicoes/colar.txt)")
            else:
                self.load_text(text)
        elif key == pygame.K_s:
            total = save_position("go", self.export_text())
            self.toast(f"Posição salva ({total} em posicoes/go.txt)")
        elif key == pygame.K_l:
            items = load_positions("go")
            if not items:
                self.toast("Nenhuma posição salva ainda (Ctrl+S salva)")
            else:
                self.saved_index = (self.saved_index + 1) % len(items)
                if self.load_text(items[self.saved_index]):
                    self.toast(f"Posição salva {self.saved_index + 1}/{len(items)}")
        else:
            return False
        return True

    def set_size(self, n):
        self.game.size = n
        self.game.reset(n)
        self.free_board = gr.GoBoard(n)
        self.counted = None
        self.drop = None
        self._setup()
        self.emit("sheen")
        self.toast(f"Goban {n}x{n}")

    # ------------------------------------------------------------ entrada
    def click(self, pt, shift=False):
        if pt is None:
            return
        g = self.game
        x, y = pt
        if self.mode == "livre":
            fb = self.free_board
            if fb.get(x, y) != gr.EMPTY:
                self._burst(x, y, fb.get(x, y), 30)
                fb.set(x, y, gr.EMPTY)
            else:
                fb.set(x, y, gr.opp(self.free_color) if shift else self.free_color)
                self.drop = (x, y, self.time)
            return
        if g.phase == "scoring":
            if g.board.get(x, y) != gr.EMPTY:
                g.toggle_dead(x, y)
                self.emit("shake", 1)
            return
        if g.phase != "play":
            return
        mover = g.turn
        ok, msg, captured = g.try_play(x, y)
        if not ok:
            self.toast(msg)
            self.emit("shake", 2)
            return
        self.drop = (x, y, self.time)
        if captured:
            for cx, cy in captured:
                self._burst(cx, cy, gr.opp(mover))
            px, py = self.point_xy(x, y)
            self.emit("popup", f"+{len(captured)}", (90, 170, 255) if mover == gr.BLACK else (255, 90, 90),
                      (px, py))
            self.emit("shake", 2 + len(captured))
            if len(captured) >= 5:
                self.emit("banner", "CAPTURA GRANDE!", (255, 214, 90))

    def _burst(self, x, y, color, power=55):
        px, py = self.point_xy(x, y)
        self.particles.burst_sprite(self.stones[color], px, py, power)

    def key(self, key, mod):
        g = self.game
        shift = bool(mod & pygame.KMOD_SHIFT)
        if self.training_key(key, mod):
            return True
        if key == pygame.K_r:
            self.reset(standard=shift)
            return True
        if key == pygame.K_y:
            self.redo()
            return True
        if key == pygame.K_d and self.mode == "jogo":
            cur = g.handicap
            nxt = {0: 2}.get(cur, cur + 1 if cur < 9 else 0)
            if g.set_handicap(nxt):
                self.counted = None
                self.drop = None
                self.emit("sheen")
                self.toast(f"Handicap {nxt} (komi 0.5, brancas começam)" if nxt else "Sem handicap")
            else:
                self.toast("Handicap só antes da primeira jogada (R recomeça)")
            return True
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
                self.start_from_free(gr.opp(self.free_color) if shift else self.free_color)
                return True
            return False
        if key == pygame.K_p and g.phase == "play":
            g.pass_turn()
            if g.phase == "scoring":
                self.emit("banner", "CONTAGEM!", (255, 214, 90))
                self.emit("sheen")
                self.toast("Clique nos grupos mortos. Enter confirma")
            else:
                self.toast(f"{NAME[gr.opp(g.turn)]} passaram")
            return True
        if key == pygame.K_g and g.phase == "play":
            g.resign()
            self._sync_tally()
            self.emit("banner", "DESISTÊNCIA", (255, 150, 90))
            self.toast(g.final["text"])
            return True
        if g.phase == "scoring":
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                g.finish_scoring()
                self._sync_tally()
                w = g.final["winner"]
                self.emit("banner", f"{NAME[w].upper()} VENCEM!" if w else "EMPATE!", (255, 214, 90))
                self.emit("confetti")
                self.emit("shake", 6)
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
    def draw_board(self, surf):
        surf.blit(self._static_surface(), (0, 0))
        g, t = self.game, self.time
        n = g.size
        board = self.board()
        livre = self.mode == "livre"
        dead = g.dead if g.phase in ("scoring", "over") and not livre else set()

        terr = None
        if g.phase in ("scoring", "over") and not livre:
            terr = dict(g.area_score()["terr_map"])
            for (x, y) in dead:
                terr[(x, y)] = gr.opp(board.get(x, y))
        elif self.show_terr:
            terr = self.estimate()["terr_map"]

        for y in range(n):
            for x in range(n):
                c = board.get(x, y)
                if c == gr.EMPTY:
                    continue
                px, py = self.point_xy(x, y)
                spr = self.stones[c]
                if self.drop and (x, y) == self.drop[:2]:
                    k = (t - self.drop[2]) / DROP_TIME
                    if k < 1.0:
                        sc = 1.0 + (1.0 - ease_out_back(k, 2.5)) * 0.8
                        d = spr.get_width()
                        spr = pygame.transform.scale(spr, (max(2, round(d * sc)), max(2, round(d * sc))))
                if (x, y) in dead:
                    spr = spr.copy()
                    spr.set_alpha(110)
                w = spr.get_width()
                shadow = pygame.Surface((w, w), pygame.SRCALPHA)
                pygame.draw.ellipse(shadow, (40, 20, 10, 90), (0, 0, w, w))
                surf.blit(shadow, (px - w // 2 + 1, py - w // 2 + 1))
                surf.blit(spr, (px - w // 2, py - w // 2))
                if (x, y) in dead:
                    r = max(2, self.cell // 4)
                    pygame.draw.line(surf, (255, 70, 70), (px - r, py - r), (px + r, py + r))
                    pygame.draw.line(surf, (255, 70, 70), (px - r, py + r), (px + r, py - r))

        if terr:
            pulse = 1 if int(t * 3) % 2 else 0
            for (x, y), owner in terr.items():
                px, py = self.point_xy(x, y)
                r = max(1, self.cell // 7) + pulse
                col = (30, 28, 40) if owner == gr.BLACK else (250, 250, 245)
                pygame.draw.rect(surf, OUTLINE, (px - r - 1, py - r - 1, 2 * r + 2, 2 * r + 2))
                pygame.draw.rect(surf, col, (px - r, py - r, 2 * r, 2 * r))

        if self.mode == "jogo" and isinstance(g.last_move, tuple):
            x, y = g.last_move
            if board.get(x, y) != gr.EMPTY:
                px, py = self.point_xy(x, y)
                r = max(1, self.cell // 6)
                pygame.draw.rect(surf, (255, 70, 70), (px - r, py - r, 2 * r, 2 * r))

        if self.hover:
            x, y = self.hover
            px, py = self.point_xy(x, y)
            h = self.cell // 2
            ok = (self.mode == "livre" and board.get(x, y) == gr.EMPTY) or \
                 (self.mode == "jogo" and g.phase == "play" and self.hover_legal())
            if ok:
                c = self.free_color if self.mode == "livre" else g.turn
                ghost = self.stones[c].copy()
                ghost.set_alpha(140 + int(60 * math.sin(t * 6)))
                w = ghost.get_width()
                surf.blit(ghost, (px - w // 2, py - w // 2 - 1))
            col = (255, 238, 120) if ok else (255, 90, 90)
            b = 1 if int(t * 4) % 2 else 0
            pygame.draw.rect(surf, col, (px - h - b, py - h - b, 2 * (h + b) + 1, 2 * (h + b) + 1), 1)
        self.particles.draw(surf)

    # ------------------------------------------------------------ HUD
    def hud(self):
        g = self.game
        d = {"title": "GO", "mode": f"{g.size}x{g.size}  ·  " + ("Modo Jogo" if self.mode == "jogo" else "Modo Livre"),
             "accent": (32, 190, 160), "lines": [], "icons": None,
             "tally": ("PARTIDAS", f"{self.tally[gr.BLACK]}", f"{self.tally[gr.WHITE]}"),
             "tally_names": ("P", "B")}
        cap = (f"Capturas  Pretas {g.captures[gr.BLACK]}  ·  Brancas {g.captures[gr.WHITE]}", (200, 210, 230))
        if self.mode == "livre":
            est = self.estimate()
            d["scores"] = [("PRETAS", est["black"], (60, 60, 80)), ("BRANCAS", est["white"], (230, 226, 210))]
            d["status"] = (f"Clique põe pedras {NAME[self.free_color].lower()}", (255, 255, 255))
            d["lines"] += [("Estimativa por área, komi " + f"{g.komi:g}", (200, 210, 230)),
                           ("Enter: jogar desta posição", (150, 240, 170))]
            d["hints"] = [("Clique", "pôr/tirar"), ("C", "cor"), ("Enter", "jogar"), ("R", "limpar"),
                          ("B", "tamanho"), ("T", "território"), ("M", "jogo")]
            return d
        if g.phase == "play":
            est = self.estimate()
            d["scores"] = [("PRETAS", est["black"], (60, 60, 80)), ("BRANCAS", est["white"], (230, 226, 210))]
            last = ""
            if g.last_move == "pass":
                last = " (passou)"
            elif isinstance(g.last_move, tuple):
                last = f" (último {gr.coord_name(*g.last_move)})"
            d["status"] = (f"Vez das {NAME[g.turn]}{last}", (255, 255, 255))
            diff = est["black"] - est["white"]
            lead = "empate" if diff == 0 else (f"Pretas +{diff:g}" if diff > 0 else f"Brancas +{-diff:g}")
            ha = f", handicap {g.handicap}" if g.handicap else ""
            d["lines"] += [(f"Estimativa: {lead} (komi {g.komi:g}{ha})", (200, 210, 230)), cap]
            d["hints"] = [("Clique", "jogar"), ("P", "passar"), ("Z", "volta"), ("Y", "avança"),
                          ("D", "handicap"), ("K", "komi"), ("B", "tamanho"), ("T", "território"),
                          ("G", "desistir"), ("R", "recomeça"), ("M", "livre")]
        elif g.phase == "scoring":
            s = g.area_score()
            d["scores"] = [("PRETAS", s["black"], (60, 60, 80)), ("BRANCAS", s["white"], (230, 226, 210))]
            d["status"] = ("CONTAGEM!", (255, 230, 120))
            d["lines"] += [("Clique nos grupos mortos (X vermelho)", (255, 230, 150)),
                           ("Área (chinesa), komi " + f"{g.komi:g}", (200, 210, 230)),
                           (f"Território: P {s['jp_black']:g}  ·  B {s['jp_white']:g}", (190, 200, 230))]
            d["hints"] = [("Clique", "morta/viva"), ("Enter", "confirmar"), ("U", "sugerir"),
                          ("V", "voltar"), ("Z", "desfazer")]
        else:
            f = g.final
            d["scores"] = [("PRETAS", f["black"], (60, 60, 80)), ("BRANCAS", f["white"], (230, 226, 210))]
            d["status"] = (f["text"], (255, 214, 90))
            if f.get("margin") is not None:
                d["lines"].append((f"Território: P {f['jp_black']:g}  ·  B {f['jp_white']:g}", (190, 200, 230)))
            d["lines"].append(cap)
            d["hints"] = [("R", "nova"), ("Z", "desfazer"), ("K", "komi"), ("B", "tamanho"), ("M", "livre")]
        return d
