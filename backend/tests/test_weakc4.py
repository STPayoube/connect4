import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from weakc4 import AI, Connect4, LEVEL_TO_DEPTH, Tree


def make_game(rows=6, cols=7, align=4, starting_player=1):
    players = {
        1: ["Player 1", 1, "X"],
        2: ["Player 2", 2, "O"],
    }
    return Connect4(players, starting_player, row=rows, col=cols, align=align, verbose=False)


def test_drop_token_and_valid_columns():
    c4 = make_game(rows=4, cols=4, align=3)
    assert c4.get_valid_columns() == [0, 1, 2, 3]
    for expected_row in [3, 2, 1, 0]:
        r, c = c4.drop_token(1, 1)
        assert (r, c) == (expected_row, 1)
    assert 1 not in c4.get_valid_columns()
    with pytest.raises(ValueError):
        c4.drop_token(1, 1)
    with pytest.raises(ValueError):
        c4.drop_token(9, 1)


def test_win_detection_horizontal_vertical_and_diagonals():
    c4 = make_game()
    for c in [1, 2, 3, 4]:
        c4.drop_token(c, 1)
    winner, cells = c4.check_win()
    assert winner == 1
    assert cells == [[5, 1], [5, 2], [5, 3], [5, 4]]
    assert c4.check_win1()[0] == 1

    c4 = make_game()
    for _ in range(4):
        c4.drop_token(3, 2)
    winner, cells = c4.check_win()
    assert winner == 2
    assert cells == [[2, 3], [3, 3], [4, 3], [5, 3]]

    c4 = make_game()
    c4.drop_token(0, 1)
    c4.drop_token(1, 2)
    c4.drop_token(1, 1)
    c4.drop_token(2, 2)
    c4.drop_token(2, 2)
    c4.drop_token(2, 1)
    c4.drop_token(3, 2)
    c4.drop_token(3, 2)
    c4.drop_token(3, 2)
    c4.drop_token(3, 1)
    winner, cells = c4.check_win()
    assert winner == 1
    assert cells == [[2, 3], [3, 2], [4, 1], [5, 0]]

    c4 = make_game(rows=5, cols=5, align=3)
    c4.grid[4][3] = 2
    c4.grid[3][2] = 2
    c4.grid[2][1] = 2
    winner, cells = c4.check_win()
    assert winner == 2
    assert cells == [[2, 1], [3, 2], [4, 3]]


def test_ai_opening_move_no_global_state_and_bounds_safe():
    c4 = make_game(rows=8, cols=4, align=3, starting_player=1)
    ai = AI("AI", 1, "X", level="medium")
    result = ai.choose_move(c4)
    assert result["row"] == 7
    assert 0 <= result["col"] < 4
    assert result["ai_info"]["level"] == "medium"
    assert c4.grid[result["row"]][result["col"]] == 1


def test_all_levels_take_win_and_block():
    for level in LEVEL_TO_DEPTH:
        c4 = make_game()
        for _ in range(3):
            c4.drop_token(2, 2)
        ai = AI("AI", 2, "O", level=level)
        res = ai.choose_move(c4)
        assert (res["row"], res["col"]) == (2, 2)
        assert c4.check_win()[0] == 2

        c4 = make_game()
        for _ in range(3):
            c4.drop_token(4, 1)
        ai = AI("AI", 2, "O", level=level)
        res = ai.choose_move(c4)
        assert (res["row"], res["col"]) == (2, 4)


def test_hard_and_impossible_use_minimax_and_block_open_two_threat():
    # Open 2-in-a-row on bottom row: _ 1 1 _ -> hard AI must block col 1 or col 4
    c4 = make_game()
    c4.drop_token(2, 1)
    c4.drop_token(3, 1)
    c4.drop_token(0, 2)
    ai = AI("Hard AI", 2, "O", level="hard")
    res = ai.choose_move(c4)
    assert res["ai_info"]["strategy"] == "minimax"
    assert res["col"] in (1, 4)


def test_tree_minimax_and_top_row_bounds_safety():
    c4_direct = make_game(rows=4, cols=4, align=3, starting_player=2)
    c4_direct.drop_token(0, 1)
    root = Tree(1, c4_direct, None, current_player=2, next_player_val=1, verbose=False)
    next_id = root.build_tree(2)
    assert next_id > 5
    root.propagate_scores(ai_value=2)
    assert len(root.best_child) >= 1

    c4 = make_game(rows=4, cols=4, align=3, starting_player=2)
    c4.grid = [
        [1, 2, 0, 0],
        [2, 1, 0, 0],
        [1, 2, 0, 0],
        [2, 1, 0, 0],
    ]
    moves = c4._get_better_move(2)
    for coord_str in moves:
        r, c = map(int, coord_str.split(":"))
        assert c4.is_playable_cell(r, c)
