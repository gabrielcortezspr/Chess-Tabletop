from tabletop import go_rules as gr


def put(g, moves):
    for x, y in moves:
        ok, msg, _ = g.try_play(x, y)
        assert ok, (x, y, msg)


def test_capture():
    g = gr.GoGame(9)
    # pretas cercam a pedra branca em (1,1)
    put(g, [(1, 0), (1, 1), (0, 1), (8, 8), (2, 1), (8, 7)])
    ok, _, cap = g.try_play(1, 2)
    assert ok and cap == [(1, 1)]
    assert g.captures[gr.BLACK] == 1
    assert g.board.get(1, 1) == gr.EMPTY


def test_suicide_forbidden():
    g = gr.GoGame(9)
    put(g, [(1, 0), (8, 8), (0, 1), (8, 7)])
    # vez das pretas; branca não pode jogar em (0,0)... pretas jogam qualquer, depois branca tenta
    put(g, [(5, 5)])
    ok, msg, _ = g.try_play(0, 0)
    assert not ok and "Suicídio" in msg


def test_ko():
    g = gr.GoGame(9)
    # forma de ko clássica
    put(g, [(1, 0), (2, 0), (0, 1), (3, 1), (1, 2), (2, 2), (8, 8), (1, 1)])
    # pretas capturam em (2,1)
    ok, _, cap = g.try_play(2, 1)
    assert ok and cap == [(1, 1)]
    # branca não pode recapturar imediatamente
    ok, msg, _ = g.try_play(1, 1)
    assert not ok and "Ko" in msg


def test_scoring_simple():
    g = gr.GoGame(9, komi=6.5)
    # pretas tomam a coluna 3, brancas a coluna 5
    for y in range(9):
        g.board.set(3, y, gr.BLACK)
        g.board.set(5, y, gr.WHITE)
    g.pass_turn()
    g.pass_turn()
    assert g.phase == "scoring"
    assert g.dead == set()
    s = g.area_score()
    assert s["black"] == 9 * 4          # 9 pedras + 27 território
    assert s["white"] == 9 * 4 + 6.5
    g.finish_scoring()
    assert g.phase == "over" and g.final["winner"] == gr.WHITE


def test_dead_stone_estimate():
    g = gr.GoGame(9, komi=0.5)
    for y in range(9):
        g.board.set(4, y, gr.BLACK)
    for y in (0, 1, 2, 3):
        for x in range(4):
            if (x, y) != (1, 1) and (x, y) != (2, 3):
                g.board.set(x, y, gr.BLACK)
    g.board.set(7, 6, gr.BLACK)  # pedra solitária cercada por território branco
    for y in range(9):
        g.board.set(5, y, gr.WHITE)
    dead = gr.estimate_dead(g.board)
    assert (7, 6) in dead
    g.pass_turn()
    g.pass_turn()
    assert (7, 6) in g.dead
    g.toggle_dead(7, 6)
    assert (7, 6) not in g.dead


def test_undo_and_resign():
    g = gr.GoGame(9)
    put(g, [(4, 4)])
    assert g.undo() and g.board.get(4, 4) == gr.EMPTY
    g.resign()
    assert g.phase == "over" and g.final["winner"] == gr.WHITE


def test_opening_stones_not_dead():
    b = gr.GoBoard(19)
    for x, y, c in [(3, 3, gr.BLACK), (15, 15, gr.WHITE), (15, 3, gr.WHITE), (3, 15, gr.WHITE),
                    (9, 9, gr.BLACK)]:
        b.set(x, y, c)
    assert gr.estimate_dead(b) == set()


def test_invader_dead_in_corner():
    b = gr.GoBoard(9)
    # muro branco forte no canto, com pedra preta invasora dentro
    for i in range(5):
        b.set(4, i, gr.WHITE)
        b.set(i, 4, gr.WHITE)
    b.set(1, 1, gr.BLACK)
    for i in range(6):
        b.set(5, i, gr.BLACK)
        b.set(i, 5, gr.BLACK)
    dead = gr.estimate_dead(b)
    assert dead == {(1, 1)}
