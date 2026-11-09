"""Regras completas de xadrez (sem dependências externas).

Casas são índices 0..63: idx = rank * 8 + file, rank 0 = fileira "1" (lado das brancas).
Peças são tuplas (cor, tipo) com cor em {"w", "b"} e tipo em "PNBRQK".
"""
from __future__ import annotations

from dataclasses import dataclass, field

WHITE, BLACK = "w", "b"
PIECE_VALUES = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0}
PIECE_NAMES_PT = {"P": "Peão", "N": "Cavalo", "B": "Bispo", "R": "Torre", "Q": "Dama", "K": "Rei"}
SAN_LETTER = {"N": "C", "B": "B", "R": "T", "Q": "D", "K": "R", "P": ""}  # notação em português

KNIGHT_D = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
KING_D = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
ROOK_D = [(1, 0), (-1, 0), (0, 1), (0, -1)]
BISHOP_D = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def other(color: str) -> str:
    return BLACK if color == WHITE else WHITE


def sq(file: int, rank: int) -> int:
    return rank * 8 + file


def file_of(s: int) -> int:
    return s % 8


def rank_of(s: int) -> int:
    return s // 8


def sq_name(s: int) -> str:
    return "abcdefgh"[file_of(s)] + str(rank_of(s) + 1)


def on_board(f: int, r: int) -> bool:
    return 0 <= f < 8 and 0 <= r < 8


@dataclass(frozen=True)
class Move:
    frm: int
    to: int
    promo: str | None = None
    castle: bool = False
    en_passant: bool = False

    def uci(self) -> str:
        return sq_name(self.frm) + sq_name(self.to) + (self.promo.lower() if self.promo else "")


def initial_board() -> list:
    b = [None] * 64
    back = "RNBQKBNR"
    for f in range(8):
        b[sq(f, 0)] = (WHITE, back[f])
        b[sq(f, 1)] = (WHITE, "P")
        b[sq(f, 6)] = (BLACK, "P")
        b[sq(f, 7)] = (BLACK, back[f])
    return b


@dataclass
class Position:
    board: list = field(default_factory=initial_board)
    turn: str = WHITE
    castling: frozenset = frozenset("KQkq")
    ep: int | None = None
    halfmove: int = 0
    fullmove: int = 1

    def copy(self) -> "Position":
        return Position(self.board[:], self.turn, self.castling, self.ep, self.halfmove, self.fullmove)

    # ------------------------------------------------------------------ ataques
    def king_square(self, color: str) -> int | None:
        for i, p in enumerate(self.board):
            if p == (color, "K"):
                return i
        return None

    def is_attacked(self, s: int, by: str) -> bool:
        b = self.board
        f, r = file_of(s), rank_of(s)
        # peões
        pr = r - 1 if by == WHITE else r + 1
        for df in (-1, 1):
            if on_board(f + df, pr) and b[sq(f + df, pr)] == (by, "P"):
                return True
        for df, dr in KNIGHT_D:
            if on_board(f + df, r + dr) and b[sq(f + df, r + dr)] == (by, "N"):
                return True
        for df, dr in KING_D:
            if on_board(f + df, r + dr) and b[sq(f + df, r + dr)] == (by, "K"):
                return True
        for dirs, kinds in ((ROOK_D, ("R", "Q")), (BISHOP_D, ("B", "Q"))):
            for df, dr in dirs:
                nf, nr = f + df, r + dr
                while on_board(nf, nr):
                    p = b[sq(nf, nr)]
                    if p is not None:
                        if p[0] == by and p[1] in kinds:
                            return True
                        break
                    nf += df
                    nr += dr
        return False

    def in_check(self, color: str | None = None) -> bool:
        color = color or self.turn
        k = self.king_square(color)
        return k is not None and self.is_attacked(k, other(color))

    # ------------------------------------------------------------------ geração
    def pseudo_moves(self):
        b, me = self.board, self.turn
        for s, p in enumerate(b):
            if p is None or p[0] != me:
                continue
            f, r = file_of(s), rank_of(s)
            kind = p[1]
            if kind == "P":
                d = 1 if me == WHITE else -1
                start = 1 if me == WHITE else 6
                last = 7 if me == WHITE else 0
                nr = r + d
                if on_board(f, nr) and b[sq(f, nr)] is None:
                    yield from self._pawn_moves(s, sq(f, nr), nr == last)
                    if r == start and b[sq(f, r + 2 * d)] is None:
                        yield Move(s, sq(f, r + 2 * d))
                for df in (-1, 1):
                    nf = f + df
                    if not on_board(nf, nr):
                        continue
                    t = sq(nf, nr)
                    if b[t] is not None and b[t][0] != me:
                        yield from self._pawn_moves(s, t, nr == last)
                    elif t == self.ep:
                        yield Move(s, t, en_passant=True)
            elif kind in "NK":
                for df, dr in (KNIGHT_D if kind == "N" else KING_D):
                    nf, nr = f + df, r + dr
                    if on_board(nf, nr):
                        t = sq(nf, nr)
                        if b[t] is None or b[t][0] != me:
                            yield Move(s, t)
                if kind == "K":
                    yield from self._castles(s)
            else:
                dirs = {"R": ROOK_D, "B": BISHOP_D, "Q": ROOK_D + BISHOP_D}[kind]
                for df, dr in dirs:
                    nf, nr = f + df, r + dr
                    while on_board(nf, nr):
                        t = sq(nf, nr)
                        if b[t] is None:
                            yield Move(s, t)
                        else:
                            if b[t][0] != me:
                                yield Move(s, t)
                            break
                        nf += df
                        nr += dr

    @staticmethod
    def _pawn_moves(frm, to, promotes):
        if promotes:
            for k in "QRBN":
                yield Move(frm, to, promo=k)
        else:
            yield Move(frm, to)

    def _castles(self, ks):
        me, b = self.turn, self.board
        rank = 0 if me == WHITE else 7
        if ks != sq(4, rank) or self.in_check(me):
            return
        opp = other(me)
        rights = ("K", "Q") if me == WHITE else ("k", "q")
        # roque pequeno
        if rights[0] in self.castling and b[sq(7, rank)] == (me, "R"):
            if b[sq(5, rank)] is None and b[sq(6, rank)] is None:
                if not self.is_attacked(sq(5, rank), opp) and not self.is_attacked(sq(6, rank), opp):
                    yield Move(ks, sq(6, rank), castle=True)
        # roque grande
        if rights[1] in self.castling and b[sq(0, rank)] == (me, "R"):
            if all(b[sq(f, rank)] is None for f in (1, 2, 3)):
                if not self.is_attacked(sq(3, rank), opp) and not self.is_attacked(sq(2, rank), opp):
                    yield Move(ks, sq(2, rank), castle=True)

    def legal_moves(self) -> list:
        out = []
        for m in self.pseudo_moves():
            nxt = self.apply(m)
            if not nxt.in_check(self.turn):
                out.append(m)
        return out

    # ------------------------------------------------------------------ aplicar
    def apply(self, m: Move) -> "Position":
        p = self.copy()
        b = p.board
        piece = b[m.frm]
        captured = b[m.to]
        me = self.turn
        b[m.to] = (me, m.promo) if m.promo else piece
        b[m.frm] = None
        if m.en_passant:
            b[sq(file_of(m.to), rank_of(m.frm))] = None
            captured = (other(me), "P")
        if m.castle:
            rank = rank_of(m.frm)
            if file_of(m.to) == 6:
                b[sq(5, rank)], b[sq(7, rank)] = b[sq(7, rank)], None
            else:
                b[sq(3, rank)], b[sq(0, rank)] = b[sq(0, rank)], None
        # direitos de roque
        rights = set(self.castling)
        for s, lost in ((sq(4, 0), "KQ"), (sq(4, 7), "kq"), (sq(0, 0), "Q"), (sq(7, 0), "K"),
                        (sq(0, 7), "q"), (sq(7, 7), "k")):
            if m.frm == s or m.to == s:
                rights -= set(lost)
        p.castling = frozenset(rights)
        p.ep = None
        if piece[1] == "P" and abs(rank_of(m.to) - rank_of(m.frm)) == 2:
            p.ep = (m.frm + m.to) // 2
        p.halfmove = 0 if (piece[1] == "P" or captured) else self.halfmove + 1
        if me == BLACK:
            p.fullmove += 1
        p.turn = other(me)
        return p

    def repetition_key(self):
        # en passant só conta se houver captura possível de fato
        ep = None
        if self.ep is not None:
            if any(m.en_passant for m in self.legal_moves()):
                ep = self.ep
        return (tuple(self.board), self.turn, self.castling, ep)

    def material(self, color: str) -> int:
        return sum(PIECE_VALUES[p[1]] for p in self.board if p and p[0] == color)

    def insufficient_material(self) -> bool:
        pieces = [(i, p) for i, p in enumerate(self.board) if p and p[1] != "K"]
        if not pieces:
            return True
        if any(p[1] in "PRQ" for _, p in pieces):
            return False
        if len(pieces) == 1:
            return True  # K+B x K ou K+N x K
        # apenas bispos, todos na mesma cor de casa
        if all(p[1] == "B" for _, p in pieces):
            colors = {(file_of(i) + rank_of(i)) % 2 for i, _ in pieces}
            return len(colors) == 1
        return False

    def to_fen(self) -> str:
        rows = []
        for r in range(7, -1, -1):
            row, empty = "", 0
            for f in range(8):
                p = self.board[sq(f, r)]
                if p is None:
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                row += p[1] if p[0] == WHITE else p[1].lower()
            if empty:
                row += str(empty)
            rows.append(row)
        cast = "".join(c for c in "KQkq" if c in self.castling) or "-"
        ep = sq_name(self.ep) if self.ep is not None else "-"
        return f"{'/'.join(rows)} {self.turn} {cast} {ep} {self.halfmove} {self.fullmove}"

    @classmethod
    def from_fen(cls, fen: str) -> "Position":
        parts = fen.split()
        board = [None] * 64
        for i, row in enumerate(parts[0].split("/")):
            r, f = 7 - i, 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                else:
                    board[sq(f, r)] = (WHITE if ch.isupper() else BLACK, ch.upper())
                    f += 1
        turn = parts[1] if len(parts) > 1 else WHITE
        cast = frozenset(parts[2]) - {"-"} if len(parts) > 2 else frozenset()
        ep = None
        if len(parts) > 3 and parts[3] != "-":
            ep = sq("abcdefgh".index(parts[3][0]), int(parts[3][1]) - 1)
        half = int(parts[4]) if len(parts) > 4 else 0
        full = int(parts[5]) if len(parts) > 5 else 1
        return cls(board, turn, frozenset(cast), ep, half, full)


def validate_position(pos: Position) -> str | None:
    """Retorna None se a posição é jogável, senão uma mensagem de erro em português."""
    b = pos.board
    for color, name in ((WHITE, "brancas"), (BLACK, "pretas")):
        n = sum(1 for p in b if p == (color, "K"))
        if n != 1:
            return f"As {name} precisam de exatamente 1 rei (têm {n})."
    for f in range(8):
        for r in (0, 7):
            p = b[sq(f, r)]
            if p and p[1] == "P":
                return "Peões não podem ficar na primeira ou última fileira."
    if pos.in_check(other(pos.turn)):
        return "O lado que não joga está em xeque."
    return None


def infer_castling(board: list) -> frozenset:
    rights = set()
    if board[sq(4, 0)] == (WHITE, "K"):
        if board[sq(7, 0)] == (WHITE, "R"):
            rights.add("K")
        if board[sq(0, 0)] == (WHITE, "R"):
            rights.add("Q")
    if board[sq(4, 7)] == (BLACK, "K"):
        if board[sq(7, 7)] == (BLACK, "R"):
            rights.add("k")
        if board[sq(0, 7)] == (BLACK, "R"):
            rights.add("q")
    return frozenset(rights)


class ChessGame:
    """Partida com histórico, desfazer, SAN, detecção de fim de jogo e material."""

    def __init__(self, position: Position | None = None):
        self.start = position.copy() if position else Position()
        self.reset(self.start)

    def reset(self, position: Position | None = None):
        self.pos = (position or Position()).copy()
        self.start = self.pos.copy()
        self.history: list = []   # (pos_antes, move, san, capturada)
        self.rep_counts: dict = {}
        self._count_rep()
        self._legal_cache = None
        self.result: str | None = None   # "1-0", "0-1", "1/2-1/2"
        self.reason: str = ""
        self.resigned = False
        self._update_result()

    def resign(self, color: str):
        """`color` desiste da partida."""
        if self.result:
            return
        self.result = "0-1" if color == WHITE else "1-0"
        self.reason = "Desistência"
        self.resigned = True
        self._legal_cache = []

    def _count_rep(self):
        k = self.pos.repetition_key()
        self.rep_counts[k] = self.rep_counts.get(k, 0) + 1

    def legal_moves(self) -> list:
        if self._legal_cache is None:
            self._legal_cache = [] if self.result else self.pos.legal_moves()
        return self._legal_cache

    def moves_from(self, s: int) -> list:
        return [m for m in self.legal_moves() if m.frm == s]

    def find_move(self, frm: int, to: int, promo: str | None = None):
        for m in self.legal_moves():
            if m.frm == frm and m.to == to and (m.promo == promo):
                return m
        return None

    def needs_promotion(self, frm: int, to: int) -> bool:
        return any(m.frm == frm and m.to == to and m.promo for m in self.legal_moves())

    def san(self, m: Move) -> str:
        pos = self.pos
        piece = pos.board[m.frm]
        if m.castle:
            s = "O-O" if file_of(m.to) == 6 else "O-O-O"
        else:
            capture = pos.board[m.to] is not None or m.en_passant
            if piece[1] == "P":
                s = ("abcdefgh"[file_of(m.frm)] + "x" if capture else "") + sq_name(m.to)
                if m.promo:
                    s += "=" + SAN_LETTER[m.promo]
            else:
                s = SAN_LETTER[piece[1]]
                others = [o for o in self.legal_moves() if o.to == m.to and o.frm != m.frm
                          and pos.board[o.frm] == piece]
                if others:
                    if all(file_of(o.frm) != file_of(m.frm) for o in others):
                        s += "abcdefgh"[file_of(m.frm)]
                    elif all(rank_of(o.frm) != rank_of(m.frm) for o in others):
                        s += str(rank_of(m.frm) + 1)
                    else:
                        s += sq_name(m.frm)
                s += ("x" if capture else "") + sq_name(m.to)
        nxt = pos.apply(m)
        if nxt.in_check():
            s += "#" if not nxt.legal_moves() else "+"
        return s

    def push(self, m: Move):
        if self.result:
            return None
        captured = self.pos.board[m.to]
        if m.en_passant:
            captured = (other(self.pos.turn), "P")
        san = self.san(m)
        self.history.append((self.pos, m, san, captured))
        self.pos = self.pos.apply(m)
        self._legal_cache = None
        self._count_rep()
        self._update_result()
        return captured

    def undo(self) -> bool:
        if self.resigned:
            self.resigned = False
            self._update_result()
            return True
        if not self.history:
            return False
        k = self.pos.repetition_key()
        self.rep_counts[k] -= 1
        prev, _, _, _ = self.history.pop()
        self.pos = prev
        self._legal_cache = None
        self.result, self.reason = None, ""
        self._update_result()
        return True

    def _update_result(self):
        self.result, self.reason = None, ""
        self._legal_cache = None
        moves = self.pos.legal_moves()
        if not moves:
            if self.pos.in_check():
                self.result = "0-1" if self.pos.turn == WHITE else "1-0"
                self.reason = "Xeque-mate"
            else:
                self.result, self.reason = "1/2-1/2", "Afogamento"
        elif self.pos.insufficient_material():
            self.result, self.reason = "1/2-1/2", "Material insuficiente"
        elif self.pos.halfmove >= 100:
            self.result, self.reason = "1/2-1/2", "Regra dos 50 lances"
        elif self.rep_counts.get(self.pos.repetition_key(), 0) >= 3:
            self.result, self.reason = "1/2-1/2", "Repetição tripla"
        self._legal_cache = [] if self.result else moves

    def captured_by(self, color: str) -> list:
        """Peças adversárias capturadas por `color`."""
        out = []
        for before, _m, _san, cap in self.history:
            if cap and before.turn == color:
                out.append(cap)
        return out

    def last_move(self):
        return self.history[-1][1] if self.history else None

    def move_list(self) -> list:
        """Lista de strings tipo '12. Cf3 Cc6'."""
        out = []
        for i, (before, _m, san, _c) in enumerate(self.history):
            if before.turn == WHITE:
                out.append(f"{before.fullmove}. {san}")
            elif i == 0:
                out.append(f"{before.fullmove}... {san}")
            else:
                out[-1] += f" {san}"
        return out

    def score(self) -> dict:
        w, b = self.pos.material(WHITE), self.pos.material(BLACK)
        return {"w": w, "b": b, "diff": w - b}
