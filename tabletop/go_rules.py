"""Regras de Go com contagem automática de pontos.

- Capturas, proibição de suicídio e de repetição de posição (superko posicional).
- Dois passes seguidos -> fase de contagem; pedras mortas são sugeridas
  automaticamente e podem ser alternadas com um clique.
- Contagem por área (regra chinesa): pedras vivas + território + komi.
  Também calculamos a contagem por território (japonesa) para referência.
"""
from __future__ import annotations

import numpy as np

EMPTY, BLACK, WHITE = 0, 1, 2
COLOR_NAME = {BLACK: "Pretas", WHITE: "Brancas"}
LETTERS = "ABCDEFGHJKLMNOPQRST"  # sem "I", como é tradição


def opp(c: int) -> int:
    return WHITE if c == BLACK else BLACK


def coord_name(x: int, y: int) -> str:
    return f"{LETTERS[x]}{y + 1}"


class GoBoard:
    def __init__(self, size: int = 19):
        self.size = size
        self.grid = [[EMPTY] * size for _ in range(size)]  # grid[y][x]

    def copy(self) -> "GoBoard":
        b = GoBoard(self.size)
        b.grid = [row[:] for row in self.grid]
        return b

    def key(self):
        return tuple(tuple(r) for r in self.grid)

    def get(self, x, y):
        return self.grid[y][x]

    def set(self, x, y, c):
        self.grid[y][x] = c

    def neighbors(self, x, y):
        s = self.size
        if x > 0:
            yield x - 1, y
        if x < s - 1:
            yield x + 1, y
        if y > 0:
            yield x, y - 1
        if y < s - 1:
            yield x, y + 1

    def group(self, x, y):
        """Retorna (pedras, liberdades) do grupo em (x, y)."""
        c = self.get(x, y)
        stones, libs, stack = {(x, y)}, set(), [(x, y)]
        while stack:
            px, py = stack.pop()
            for nx, ny in self.neighbors(px, py):
                v = self.get(nx, ny)
                if v == EMPTY:
                    libs.add((nx, ny))
                elif v == c and (nx, ny) not in stones:
                    stones.add((nx, ny))
                    stack.append((nx, ny))
        return stones, libs

    def all_groups(self):
        seen, out = set(), []
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y][x] != EMPTY and (x, y) not in seen:
                    stones, libs = self.group(x, y)
                    seen |= stones
                    out.append((self.grid[y][x], stones, libs))
        return out

    def empty_regions(self, removed=frozenset()):
        """Regiões vazias (considerando `removed` como vazias) e as cores que as cercam."""
        seen, out = set(), []

        def val(px, py):
            return EMPTY if (px, py) in removed else self.grid[py][px]

        for y in range(self.size):
            for x in range(self.size):
                if val(x, y) != EMPTY or (x, y) in seen:
                    continue
                region, border, stack = {(x, y)}, set(), [(x, y)]
                seen.add((x, y))
                while stack:
                    px, py = stack.pop()
                    for nx, ny in self.neighbors(px, py):
                        v = val(nx, ny)
                        if v == EMPTY:
                            if (nx, ny) not in seen:
                                seen.add((nx, ny))
                                region.add((nx, ny))
                                stack.append((nx, ny))
                        else:
                            border.add(v)
                out.append((region, border))
        return out

    def count(self, color):
        return sum(row.count(color) for row in self.grid)


class GoGame:
    def __init__(self, size: int = 19, komi: float = 6.5):
        self.komi = komi
        self.reset(size)

    def reset(self, size: int | None = None, board: GoBoard | None = None, turn: int = BLACK):
        if size:
            self.size = size
        self.board = board.copy() if board else GoBoard(self.size)
        self.size = self.board.size
        self.turn = turn
        self.captures = {BLACK: 0, WHITE: 0}   # pedras que cada cor capturou
        self.passes = 0
        self.phase = "play"                    # play | scoring | over
        self.dead: set = set()
        self.last_move = None                  # (x, y) ou "pass"
        self.history: list = []
        self.seen = {self.board.key()}
        self.move_number = 0
        self.final: dict | None = None
        self.resigned: int | None = None

    # ---------------------------------------------------------------- jogadas
    def _snapshot(self):
        return (self.board.copy(), self.turn, dict(self.captures), self.passes, self.phase,
                set(self.dead), self.last_move, set(self.seen), self.move_number, self.final,
                self.resigned)

    def _restore(self, snap):
        (self.board, self.turn, self.captures, self.passes, self.phase, self.dead,
         self.last_move, self.seen, self.move_number, self.final, self.resigned) = snap

    def try_play(self, x: int, y: int):
        """Tenta jogar. Retorna (ok, mensagem, capturadas)."""
        if self.phase != "play":
            return False, "A partida não está em andamento.", []
        if self.board.get(x, y) != EMPTY:
            return False, "Ponto ocupado.", []
        b = self.board.copy()
        me = self.turn
        b.set(x, y, me)
        captured = []
        for nx, ny in b.neighbors(x, y):
            if b.get(nx, ny) == opp(me):
                stones, libs = b.group(nx, ny)
                if not libs:
                    for sx, sy in stones:
                        b.set(sx, sy, EMPTY)
                    captured.extend(stones)
        _, libs = b.group(x, y)
        if not libs:
            return False, "Suicídio não é permitido.", []
        if b.key() in self.seen:
            return False, "Ko: essa posição já ocorreu.", []
        self.history.append(self._snapshot())
        self.board = b
        self.captures[me] += len(captured)
        self.seen.add(b.key())
        self.turn = opp(me)
        self.passes = 0
        self.last_move = (x, y)
        self.move_number += 1
        return True, "", captured

    def is_legal(self, x, y) -> bool:
        if self.phase != "play" or self.board.get(x, y) != EMPTY:
            return False
        snap = self._snapshot()
        hist_len = len(self.history)
        ok, _, _ = self.try_play(x, y)
        if ok:
            self._restore(snap)
            del self.history[hist_len:]
        return ok

    def pass_turn(self):
        if self.phase != "play":
            return
        self.history.append(self._snapshot())
        self.passes += 1
        self.last_move = "pass"
        self.turn = opp(self.turn)
        self.move_number += 1
        if self.passes >= 2:
            self.enter_scoring()

    def resign(self):
        if self.phase != "play":
            return
        self.history.append(self._snapshot())
        self.resigned = self.turn
        self.phase = "over"
        winner = opp(self.turn)
        self.final = {"winner": winner, "margin": None, "text": f"{COLOR_NAME[winner]} vencem por desistência",
                      **self.area_score(set())}

    def undo(self) -> bool:
        if not self.history:
            return False
        self._restore(self.history.pop())
        return True

    # ---------------------------------------------------------------- contagem
    def enter_scoring(self):
        self.phase = "scoring"
        self.dead = estimate_dead(self.board)

    def resume_play(self):
        if self.phase == "scoring":
            self.phase = "play"
            self.passes = 0
            self.dead = set()

    def toggle_dead(self, x, y):
        if self.board.get(x, y) == EMPTY:
            return
        stones, _ = self.board.group(x, y)
        if (x, y) in self.dead:
            self.dead -= stones
        else:
            self.dead |= stones

    def area_score(self, dead=None) -> dict:
        dead = self.dead if dead is None else dead
        b = self.board
        stones = {BLACK: 0, WHITE: 0}
        for y in range(b.size):
            for x in range(b.size):
                c = b.get(x, y)
                if c != EMPTY and (x, y) not in dead:
                    stones[c] += 1
        territory = {BLACK: 0, WHITE: 0}
        terr_map = {}
        for region, border in b.empty_regions(frozenset(dead)):
            if len(border) == 1:
                owner = next(iter(border))
                territory[owner] += len(region)
                for p in region:
                    terr_map[p] = owner
        dead_count = {BLACK: 0, WHITE: 0}
        for x, y in dead:
            dead_count[b.get(x, y)] += 1
        area = {c: stones[c] + territory[c] for c in (BLACK, WHITE)}
        black = area[BLACK]
        white = area[WHITE] + self.komi
        # contagem japonesa: território + prisioneiros (capturas + mortas)
        jp_black = territory[BLACK] + self.captures[BLACK] + dead_count[WHITE]
        jp_white = territory[WHITE] + self.captures[WHITE] + dead_count[BLACK] + self.komi
        return {"black": black, "white": white, "stones": stones, "territory": territory,
                "terr_map": terr_map, "jp_black": jp_black, "jp_white": jp_white,
                "dead_count": dead_count}

    def finish_scoring(self):
        if self.phase != "scoring":
            return
        self.history.append(self._snapshot())
        s = self.area_score()
        margin = s["black"] - s["white"]
        if margin > 0:
            winner, text = BLACK, f"Pretas vencem por {margin:g} pontos"
        elif margin < 0:
            winner, text = WHITE, f"Brancas vencem por {-margin:g} pontos"
        else:
            winner, text = None, "Empate (jigo)"
        self.final = {"winner": winner, "margin": abs(margin), "text": text, **s}
        self.phase = "over"

    def estimate(self) -> dict:
        """Estimativa ao vivo durante a partida (influência + mortas sugeridas)."""
        dead = estimate_dead(self.board)
        infl = influence(self.board, dead)
        black = white = 0.0
        terr_map = {}
        b = self.board
        for y in range(b.size):
            for x in range(b.size):
                c = b.get(x, y)
                if c != EMPTY and (x, y) not in dead:
                    if c == BLACK:
                        black += 1
                    else:
                        white += 1
                    continue
                v = infl[y, x]
                if v > 0.35:
                    black += 1
                    terr_map[(x, y)] = BLACK
                elif v < -0.35:
                    white += 1
                    terr_map[(x, y)] = WHITE
        white += self.komi
        return {"black": black, "white": white, "terr_map": terr_map, "dead": dead}


# ----------------------------------------------------------------- heurísticas

def influence(board: GoBoard, dead=frozenset(), radius: int = 4) -> np.ndarray:
    n = board.size
    src = np.zeros((n, n), dtype=np.float32)
    for y in range(n):
        for x in range(n):
            c = board.get(x, y)
            if c != EMPTY and (x, y) not in dead:
                src[y, x] = 1.0 if c == BLACK else -1.0
    out = np.zeros_like(src)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            d = abs(dx) + abs(dy)
            if d > radius:
                continue
            w = 1.0 / (1.0 + d * d)
            ys0, ys1 = max(0, -dy), min(n, n - dy)
            xs0, xs1 = max(0, -dx), min(n, n - dx)
            out[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx] += w * src[ys0:ys1, xs0:xs1]
    return out


def count_eyes(board: GoBoard, color: int, stones: set, regions=None) -> int:
    """Conta regiões vazias pequenas cercadas apenas por `color` e adjacentes ao grupo."""
    eyes = 0
    for region, border in (regions if regions is not None else board.empty_regions()):
        if border != {color} or len(region) > 8:
            continue
        touches = any(n in stones for p in region for n in board.neighbors(*p))
        if touches:
            eyes += 1
    return eyes


def _conv(board: GoBoard, color: int, radius: int = 4) -> np.ndarray:
    n = board.size
    src = np.array([[1.0 if board.get(x, y) == color else 0.0 for x in range(n)] for y in range(n)],
                   dtype=np.float32)
    out = np.zeros_like(src)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            d = abs(dx) + abs(dy)
            if d > radius:
                continue
            w = 1.0 / (1.0 + d * d)
            ys0, ys1 = max(0, -dy), min(n, n - dy)
            xs0, xs1 = max(0, -dx), min(n, n - dx)
            out[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx] += w * src[ys0:ys1, xs0:xs1]
    return out


def estimate_dead(board: GoBoard, depth: int = 3, ratio: float = 1.5) -> set:
    """Sugestão automática de pedras mortas.

    Para cada grupo sem dois olhos, olhamos a vizinhança que ele alcança
    (andando por pontos vazios ou da própria cor, até `depth` passos) e
    comparamos a influência amiga (só de pedras alcançáveis) com a
    adversária nessa área. Se o
    adversário domina com folga, o grupo é considerado morto.
    """
    dead = set()
    groups = board.all_groups()
    if not groups:
        return dead
    infl = {BLACK: _conv(board, BLACK), WHITE: _conv(board, WHITE)}

    def w(d):
        return 1.0 / (1.0 + d * d) if d <= 4 else 0.0

    regions = board.empty_regions()
    for color, stones, libs in groups:
        if count_eyes(board, color, stones, regions) >= 2:
            continue
        near, frontier = set(stones), list(stones)
        for _ in range(depth):
            nxt = []
            for p in frontier:
                for q in board.neighbors(*p):
                    if q not in near and board.get(*q) in (EMPTY, color):
                        near.add(q)
                        nxt.append(q)
            frontier = nxt
        # influência amiga só das pedras alcançáveis (não "atravessa" muros adversários)
        friends = [p for p in near if board.get(*p) == color]
        own = sum(w(abs(px - fx) + abs(py - fy)) for px, py in near for fx, fy in friends)
        foe = sum(float(infl[opp(color)][y, x]) for x, y in near)
        if foe > ratio * own:
            dead |= stones
    return dead
