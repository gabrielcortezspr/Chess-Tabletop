import pytest

from tabletop import chess_rules as cr


def perft(pos, depth):
    if depth == 0:
        return 1
    moves = pos.legal_moves()
    if depth == 1:
        return len(moves)
    return sum(perft(pos.apply(m), depth - 1) for m in moves)


@pytest.mark.parametrize("fen,depth,expected", [
    ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", 3, 8902),
    ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", 2, 2039),
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", 4, 43238),
    ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", 3, 9467),
    ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", 2, 1486),
])
def test_perft(fen, depth, expected):
    assert perft(cr.Position.from_fen(fen), depth) == expected


def test_fen_roundtrip():
    fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    assert cr.Position.from_fen(fen).to_fen() == fen


def play(g, *ucis):
    for u in ucis:
        frm = cr.sq("abcdefgh".index(u[0]), int(u[1]) - 1)
        to = cr.sq("abcdefgh".index(u[2]), int(u[3]) - 1)
        promo = u[4].upper() if len(u) > 4 else None
        m = g.find_move(frm, to, promo)
        assert m is not None, u
        g.push(m)


def test_fools_mate_and_undo():
    g = cr.ChessGame()
    play(g, "f2f3", "e7e5", "g2g4", "d8h4")
    assert g.result == "0-1" and g.reason == "Xeque-mate"
    assert g.history[-1][2] == "Dh4#"
    assert g.undo()
    assert g.result is None


def test_stalemate():
    g = cr.ChessGame(cr.Position.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"))
    assert g.result == "1/2-1/2" and g.reason == "Afogamento"


def test_threefold():
    g = cr.ChessGame()
    play(g, "g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1", "f6g8")
    assert g.result == "1/2-1/2" and g.reason == "Repetição tripla"


def test_insufficient():
    g = cr.ChessGame(cr.Position.from_fen("8/8/4k3/8/8/2KB4/8/8 w - - 0 1"))
    assert g.result == "1/2-1/2"


def test_material_and_captures():
    g = cr.ChessGame()
    play(g, "e2e4", "d7d5", "e4d5", "d8d5")
    assert g.score() == {"w": 38, "b": 38, "diff": 0}
    assert g.captured_by("w") == [("b", "P")]
    assert g.captured_by("b") == [("w", "P")]


def test_promotion_san():
    g = cr.ChessGame(cr.Position.from_fen("8/P6k/8/8/8/8/8/K7 w - - 0 1"))
    assert g.needs_promotion(cr.sq(0, 6), cr.sq(0, 7))
    play(g, "a7a8n")
    assert g.pos.board[cr.sq(0, 7)] == ("w", "N")
    assert g.history[-1][2] == "a8=C"


def test_validate_and_resign():
    pos = cr.Position.from_fen("8/8/8/8/8/8/8/K7 w - - 0 1")
    assert cr.validate_position(pos) is not None
    g = cr.ChessGame()
    g.resign("w")
    assert g.result == "0-1"
    assert g.undo() and g.result is None
