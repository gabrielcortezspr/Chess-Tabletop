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


# ---------------------------------------------------------------- auditoria de regras

def moves_uci(fen):
    return {m.uci() for m in cr.Position.from_fen(fen).legal_moves()}


def test_castling_rules():
    # roque permitido
    assert "e1g1" in moves_uci("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert "e1c1" in moves_uci("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    # não pode passar por casa atacada (f1 atacada pela torre em f8)
    assert "e1g1" not in moves_uci("5r1k/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    # não pode rocar em xeque
    assert "e1g1" not in moves_uci("4r2k/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    # roque grande: b1 atacada não impede
    assert "e1c1" in moves_uci("1r5k/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    # sem direito, sem roque
    assert "e1g1" not in moves_uci("7k/8/8/8/8/8/8/R3K2R w Q - 0 1")


def test_castling_rights_lost_when_rook_captured():
    g = cr.ChessGame(cr.Position.from_fen("r3k2r/8/8/8/8/8/6b1/R3K2R b KQkq - 0 1"))
    play(g, "g2h1")
    assert "K" not in g.pos.castling and "Q" in g.pos.castling


def test_en_passant_and_pin():
    assert "e5d6" in moves_uci("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    # en passant que deixaria o rei em xeque pela torre na mesma fileira é ilegal
    assert "e5d6" not in moves_uci("8/8/8/r2pP2K/8/8/8/4k3 w - d6 0 1")
    # en passant só no lance imediatamente seguinte
    g = cr.ChessGame(cr.Position.from_fen("4k3/3p4/8/4P3/8/8/8/4K3 b - - 0 1"))
    play(g, "d7d5")
    assert g.find_move(cr.sq(4, 4), cr.sq(3, 5)) is not None
    play(g, "e1e2", "e8e7")
    assert g.find_move(cr.sq(4, 4), cr.sq(3, 5)) is None


def test_fifty_move_rule():
    g = cr.ChessGame(cr.Position.from_fen("4k3/8/8/8/8/8/R7/4K3 w - - 99 80"))
    assert g.result is None
    play(g, "a2a3")
    assert g.result == "1/2-1/2" and g.reason == "Regra dos 50 lances"


def test_mate_beats_fifty_moves():
    g = cr.ChessGame(cr.Position.from_fen("7k/8/6K1/8/8/8/8/R7 w - - 99 80"))
    play(g, "a1a8")
    assert g.reason == "Xeque-mate"


def test_insufficient_material_cases():
    def ins(fen):
        return cr.Position.from_fen(fen).insufficient_material()
    assert ins("8/8/4k3/8/8/2K5/8/8 w - - 0 1")
    assert ins("8/8/4k3/8/8/2KN4/8/8 w - - 0 1")
    assert not ins("8/8/4k3/8/8/2KNN3/8/8 w - - 0 1")       # dois cavalos: mate possível
    assert not ins("8/8/4kb2/8/8/2KB4/8/8 w - - 0 1")       # bispos de cores diferentes
    assert not ins("8/8/4k3/8/8/2KP4/8/8 w - - 0 1")


def test_undo_redo_and_rewind():
    g = cr.ChessGame()
    play(g, "e2e4", "e7e5", "g1f3")
    g.rewind()
    assert not g.history and len(g.redo_stack) == 3
    assert g.redo().uci() == "e2e4"
    play(g, "d7d5")                     # lance novo apaga o que havia para refazer
    assert g.redo_stack == []


def test_pgn_import_export():
    pgn = """[Event "Teste"]
    1. e4 {abertura} e5 2. Nf3 (2. f4 exf4) Nc6 3. Bb5 a6 $1 4. Ba4 Nf6 5. O-O Be7 *"""
    g = cr.parse_pgn(pgn)
    assert len(g.history) == 10
    assert g.pos.board[cr.sq(6, 0)] == ("w", "K")      # roque feito
    again = cr.parse_pgn(g.pgn())
    assert again.pos.to_fen() == g.pos.to_fen()
    # PGN com posição inicial (FEN) e notação em português
    g2 = cr.parse_pgn('[FEN "4k3/8/8/8/8/8/8/R3K3 w Q - 0 1"] 1. Ta8+ Rd7')
    assert g2.pos.board[cr.sq(0, 7)] == ("w", "R")


def test_pgn_rook_vs_portuguese_king():
    # "Rf1" no PGN internacional é torre, não rei
    g = cr.ChessGame(cr.Position.from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 0 1"))
    m = g.match_san("Rb1")
    assert m and g.pos.board[m.frm][1] == "R"


def test_invalid_fen():
    for bad in ("", "8/8/8 w - - 0 1", "rnbqkbnr/pppppppp/9/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "xnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"):
        with pytest.raises(ValueError):
            cr.Position.from_fen(bad)
