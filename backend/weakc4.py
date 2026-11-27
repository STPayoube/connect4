import copy
import random
import time

LEVEL_TO_DEPTH = {
    "easy": 1,
    "medium": 2,
    "hard": 3,
    "impossible": 4,
}

DEPTH_TO_LEVEL = {v: k for k, v in LEVEL_TO_DEPTH.items()}


class Connect4:
    def __init__(self, players, current_player, row=6, col=7, align=4, verbose=False):
        self.row = row
        self.col = col
        self.grid = [[0 for _ in range(col)] for _ in range(row)]
        self.checkgrid = [[0 for _ in range(col)] for _ in range(row)]
        self.align = align
        self.players = players
        self.current_player = current_player
        self.verbose = verbose

    def _log(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

    def print(self, grid=None):
        if grid is None:
            grid = self.grid
        print("  |", end="")
        for i in range(self.col):
            if i <= 9:
                print(f" {i} |", end="")
            else:
                print(f" {i}|", end="")
        print("")
        for r in range(self.row):
            print(r, end=" | ")
            for c in range(self.col):
                val = grid[r][c]
                if val == 0:
                    ch = " "
                elif val in self.players:
                    shape = self.players[val][2]
                    ch = "•" if shape == -1 else shape
                else:
                    ch = str(val)
                print(ch, end=" | ")
            print("")
        print("\n")

    def get_opponent(self, player_value=None):
        active = self.current_player if player_value is None else player_value
        for key in self.players.keys():
            if key != active:
                return key
        return None

    def get_drop_row(self, col):
        if col < 0 or col >= self.col:
            return None
        for r in range(self.row - 1, -1, -1):
            if self.grid[r][col] == 0:
                return r
        return None

    def get_valid_columns(self):
        return [c for c in range(self.col) if self.grid[0][c] == 0]

    def is_full(self):
        return len(self.get_valid_columns()) == 0

    def is_playable_cell(self, row, col):
        if not (0 <= row < self.row and 0 <= col < self.col):
            return False
        if self.grid[row][col] != 0:
            return False
        return row == self.row - 1 or self.grid[row + 1][col] != 0

    def drop_token(self, col, player_value=None):
        if col < 0 or col >= self.col:
            raise ValueError(f"Column {col} is out of bounds (0..{self.col - 1}).")
        row = self.get_drop_row(col)
        if row is None:
            raise ValueError(f"Column {col} is full.")
        val = self.current_player if player_value is None else player_value
        self.grid[row][col] = val
        return row, col

    def has_win_at(self, row, col, val):
        """Fast O(align) win check centered on a newly placed token."""
        directions = ((0, 1), (1, 0), (1, 1), (1, -1))
        for dr, dc in directions:
            count = 1
            r, c = row + dr, col + dc
            while 0 <= r < self.row and 0 <= c < self.col and self.grid[r][c] == val:
                count += 1
                r += dr
                c += dc
            r, c = row - dr, col - dc
            while 0 <= r < self.row and 0 <= c < self.col and self.grid[r][c] == val:
                count += 1
                r -= dr
                c -= dc
            if count >= self.align:
                return True
        return False

    def init_check(self):
        self.checkgrid = [[0 for _ in range(self.col)] for _ in range(self.row)]
        return [0, 0]

    def check_win1(self):
        """Scan rows, columns, and both diagonals without relying on global state."""
        # Horizontal
        self.init_check()
        for row in range(self.row):
            streak = [0, 0]
            cells = []
            for col in range(self.col - 1, -1, -1):
                self.checkgrid[row][col] = -1
                val = self.grid[row][col]
                if val != 0 and val == streak[0]:
                    streak[1] += 1
                    cells.append([row, col])
                else:
                    streak = [val, 1 if val != 0 else 0]
                    cells = [[row, col]] if val != 0 else []
                if streak[1] >= self.align and streak[0] not in (0, -1):
                    self._log("WIN - Ligne", streak)
                    return streak[0], sorted(cells)

        # Vertical
        self.init_check()
        for col in range(self.col):
            streak = [0, 0]
            cells = []
            for row in range(self.row):
                self.checkgrid[row][col] = -1
                val = self.grid[row][col]
                if val != 0 and val == streak[0]:
                    streak[1] += 1
                    cells.append([row, col])
                else:
                    streak = [val, 1 if val != 0 else 0]
                    cells = [[row, col]] if val != 0 else []
                if streak[1] >= self.align and streak[0] not in (0, -1):
                    self._log("WIN - Colonne", streak)
                    return streak[0], sorted(cells)

        # Diagonal down-right (\)
        self.init_check()
        for col in range(self.col - self.align + 1):
            for row in range(self.row - self.align + 1):
                val = self.grid[row][col]
                if val in (0, -1):
                    continue
                cells = [[row + k, col + k] for k in range(self.align)]
                for r_idx, c_idx in cells:
                    self.checkgrid[r_idx][c_idx] = -1
                if all(self.grid[r_idx][c_idx] == val for r_idx, c_idx in cells):
                    self._log("WIN - Diag 1", [val, self.align])
                    return val, sorted(cells)

        # Diagonal up-right (/)
        self.init_check()
        for col in range(self.col - self.align + 1):
            for row in range(self.row - 1, self.align - 2, -1):
                val = self.grid[row][col]
                if val in (0, -1):
                    continue
                cells = [[row - k, col + k] for k in range(self.align)]
                for r_idx, c_idx in cells:
                    self.checkgrid[r_idx][c_idx] = -1
                if all(self.grid[r_idx][c_idx] == val for r_idx, c_idx in cells):
                    self._log("WIN - Diag 2", [val, self.align])
                    return val, sorted(cells)

        return None, []

    def check_win(self):
        """Return (winner_id, winning_cells) for any player with an aligned group >= align."""
        groups = self.group_checkers()
        for player_val, player_groups in groups.items():
            winning_groups = [g for g in player_groups if len(g) >= self.align]
            if winning_groups:
                seen = set()
                winning_cells = []
                for grp in winning_groups:
                    for coord in grp:
                        key = (coord[0], coord[1])
                        if key not in seen:
                            seen.add(key)
                            winning_cells.append([coord[0], coord[1]])
                winning_cells.sort()
                self._log(f"WIN PLAYER {player_val}", winning_cells)
                return player_val, winning_cells
        return None, []

    def group_checkers(self):
        moves_dict = {}
        raw_groups_by_val = {}
        directions = [
            (-1, -1), (0, -1), (1, -1),
            (-1, 0),           (1, 0),
            (-1, 1),  (0, 1),  (1, 1),
        ]

        for row in range(self.row):
            for col in range(self.col):
                val = self.grid[row][col]

                if val != 0:
                    if val not in raw_groups_by_val:
                        raw_groups_by_val[val] = []

                    single_token = [[row, col]]
                    if single_token not in raw_groups_by_val[val]:
                        raw_groups_by_val[val].append(single_token)

                    for dr, dc in directions:
                        line = [[row, col]]
                        curr_r, curr_c = row + dr, col + dc

                        while 0 <= curr_r < self.row and 0 <= curr_c < self.col:
                            if self.grid[curr_r][curr_c] == val:
                                line.append([curr_r, curr_c])
                                curr_r += dr
                                curr_c += dc
                            else:
                                break

                        if len(line) > 1:
                            sorted_line = sorted(line)
                            if sorted_line not in raw_groups_by_val[val]:
                                raw_groups_by_val[val].append(sorted_line)

        for val, raw_groups in raw_groups_by_val.items():
            raw_groups.sort(key=len, reverse=True)
            final_list = []
            for g in raw_groups:
                is_subgroup = False
                for existing in final_list:
                    if all(coord in existing for coord in g):
                        is_subgroup = True
                        break
                if not is_subgroup:
                    final_list.append(g)

            if final_list:
                moves_dict[val] = final_list

        return moves_dict

    def empty(self):
        for row in self.grid:
            for col in row:
                if col != 0:
                    return False
        return True

    def check_dir(self, moves, player):
        """Analyse les mouvements possibles. Découpé en sous-méthodes pour la lisibilité."""
        row, col, diag1, diag2 = True, True, True, True
        move_to_play = False

        for i in range(len(moves) - 1):
            if moves[i][0] != moves[i + 1][0]:
                row = False
            if moves[i][1] != moves[i + 1][1]:
                col = False
            if not ((moves[i][0] + 1 == moves[i + 1][0]) and (moves[i][1] - 1 == moves[i + 1][1])):
                diag1 = False
            if not ((moves[i][0] + 1 == moves[i + 1][0]) and (moves[i][1] + 1 == moves[i + 1][1])):
                diag2 = False

        rowL, colL, rowR, colR = moves[0][0], moves[0][1], moves[-1][0], moves[-1][1]
        border = lambda r: r == self.row - 1

        played = False
        pts = 0

        if row:
            move_to_play, played, pts = self._check_row(
                moves, player, rowL, colL, rowR, colR, border, played, pts
            )
        if col and not played:
            move_to_play, played, pts = self._check_col(
                player, rowL, colL, rowR, colR, played, pts
            )
        if diag1 and not played:
            move_to_play, played, pts = self._check_diag1(
                player, rowL, colL, rowR, colR, border, played, pts
            )
        if diag2 and not played:
            move_to_play, played, pts = self._check_diag2(
                player, rowL, colL, rowR, colR, border, played, pts
            )

        return move_to_play, row, col, diag1, diag2, pts

    def _check_row(self, moves, player, rowL, colL, rowR, colR, border, played, pts):
        move_to_play = False
        if player == "group player counter":
            if colR < self.col - 1 and colL > 0:
                if (
                    rowL == rowR
                    and self.grid[rowR][colL - 1] == 0
                    and self.grid[rowR][colR + 1] == 0
                    and len(moves) >= 2
                ):
                    chosen_col = (
                        [colL, -1]
                        if abs(colL - round(self.col / 2)) < abs(colR - round(self.col / 2))
                        else [colR, 1]
                    )
                    target_c = chosen_col[0] + chosen_col[1]
                    if border(rowR):
                        move_to_play = [rowR, target_c]
                        played = True
                        pts = 1.5
                    elif (
                        rowR + 1 < self.row
                        and self.grid[rowR + 1][colL - 1] != 0
                        and self.grid[rowR + 1][colR + 1] != 0
                    ):
                        move_to_play = [rowR, target_c]
                        played = True
                        pts = 1.5

        if border(rowR):
            if colR < self.col - 1:
                if (
                    self.col - 1 - colL >= self.align - 1
                    and self.grid[rowR][colR + 1] == 0
                    and player in ["group ia win", "group player win", "group ia add", "group ai add", "group player counter"]
                    and not played
                ):
                    move_to_play = [rowR, colR + 1]
                    played = True
            if colL > 0 and not played:
                if (
                    colR + 1 >= self.align
                    and self.grid[rowR][colL - 1] == 0
                    and player in ["group ia win", "group player win", "group ia add", "group ai add", "group player counter"]
                ):
                    move_to_play = [rowR, colL - 1]
                    played = True
        else:
            if colR < self.col - 1 and rowR + 1 < self.row:
                if (
                    self.col - 1 - colL >= self.align - 1
                    and self.grid[rowR][colR + 1] == 0
                    and player in ["group ia win", "group player win", "group ia add", "group ai add", "group player counter"]
                ):
                    if (
                        self.grid[rowR + 1][colR + 1] != 0
                        and self.grid[rowR][colR + 1] == 0
                        and not played
                    ):
                        move_to_play = [rowR, colR + 1]
                        played = True
            if colL > 0 and rowR + 1 < self.row and not played:
                if (
                    colR + 1 >= self.align
                    and self.grid[rowR][colL - 1] == 0
                    and player in ["group ia win", "group player win", "group ia add", "group ai add", "group player counter"]
                ):
                    if (
                        self.grid[rowR + 1][colL - 1] != 0
                        and self.grid[rowR][colL - 1] == 0
                    ):
                        move_to_play = [rowR, colL - 1]
                        played = True

        return move_to_play, played, pts

    def _check_col(self, player, rowL, colL, rowR, colR, played, pts):
        move_to_play = False
        if rowL > 0 and self.grid[rowL - 1][colL] == 0 and (rowR >= self.align - 1):
            move_to_play = [rowL - 1, colL]
            self._log("COLONNE")
            played = True
        return move_to_play, played, pts

    def _check_diag1(self, player, rowL, colL, rowR, colR, border, played, pts):
        move_to_play = False
        if (
            rowL > 0
            and colL + 1 < self.col
            and not (player in ["group ia add", "group player counter"] and colL + 1 == self.col - 1 and colL - colR < self.align - 1)
        ):
            if self.grid[rowL - 1][colL + 1] == 0 and self.grid[rowL][colL + 1] != 0 and not played:
                move_to_play = [rowL - 1, colL + 1]
                played = True
                self._log("DROITE HAUT")
        if colR > 0 and rowR + 1 < self.row and not played:
            if border(rowR + 1) and self.grid[rowR + 1][colR - 1] == 0:
                move_to_play = [rowR + 1, colR - 1]
                played = True
                self._log("GAUCHE BAS (bord)")
            elif (
                rowR + 2 < self.row
                and self.grid[rowR + 1][colR - 1] == 0
                and self.grid[rowR + 2][colR - 1] != 0
            ):
                move_to_play = [rowR + 1, colR - 1]
                played = True
                self._log("GAUCHE BAS")
        self._log("DIAGONALE 1")
        return move_to_play, played, pts

    def _check_diag2(self, player, rowL, colL, rowR, colR, border, played, pts):
        move_to_play = False
        if (
            rowL > 0
            and colL > 0
            and not (player in ["group ia add", "group player counter"] and colL - 1 == 0 and colR - colL < self.align - 1)
        ):
            if self.grid[rowL - 1][colL - 1] == 0 and self.grid[rowL][colL - 1] != 0 and not played:
                move_to_play = [rowL - 1, colL - 1]
                played = True

        upper_left_blocked = (
            rowL > 0 and colL > 0 and self.grid[rowL - 1][colL - 1] != 0
        )
        if (
            colR < self.col - 1
            and rowR + 1 < self.row
            and not (player in ["group ia add", "group player counter"] and upper_left_blocked)
        ):
            if border(rowR + 1) and not played and self.grid[rowR + 1][colR + 1] == 0:
                move_to_play = [rowR + 1, colR + 1]
                played = True
            elif (
                rowR + 2 < self.row
                and not played
                and self.grid[rowR + 1][colR + 1] == 0
                and self.grid[rowR + 2][colR + 1] != 0
            ):
                move_to_play = [rowR + 1, colR + 1]
                played = True

        return move_to_play, played, pts

    def _get_better_move(self, player_value=None):
        active_player = self.current_player if player_value is None else player_value
        valeur_adversaire = self.get_opponent(active_player)

        groups = self.group_checkers()
        group_ia = groups.get(active_player, [])
        group_player = groups.get(valeur_adversaire, [])
        all_possible_moves = {}

        self._log("CURRENT PLAYER", active_player)

        if self.empty():
            center_col = self.col // 2
            return {f"{self.row - 1}:{center_col}": [999999, ["starting game"]]}

        configs = [
            [group_ia, lambda moves: len(moves) + 1 == self.align, 999999, "group ia win"],
            [group_player, lambda moves: len(moves) + 1 == self.align, 999998, "group player win"],
            [group_ia, lambda moves: True, 2, "group ia add"],
            [group_player, lambda moves: True, 1, "group player counter"],
        ]

        for group, cond, pts, name in configs:
            for moves in group:
                if cond(moves):
                    move = self.check_dir(moves, name)
                    if move[0] is not False:
                        r, c = move[0][0], move[0][1]
                        if self.is_playable_cell(r, c):
                            current_move = f"{r}:{c}"
                            if current_move not in all_possible_moves:
                                all_possible_moves[current_move] = [pts + move[5], [name]]
                            else:
                                all_possible_moves[current_move][0] += pts + move[5]
                                all_possible_moves[current_move][1].append(name)

        self._log(groups)
        return all_possible_moves


class Tree:
    def __init__(
        self,
        id,
        c4_instance,
        parent,
        children=None,
        current_player=None,
        next_player_val=None,
        move_played=None,
        verbose=False,
    ):
        self.id = id
        self.c4 = c4_instance
        self.parent = parent
        self.children = children if children is not None else []
        self.points = 0
        self.current_player = current_player if current_player is not None else c4_instance.current_player
        self.next_player_val = next_player_val if next_player_val is not None else c4_instance.get_opponent(self.current_player)
        self.c4.current_player = self.current_player
        self.verbose = verbose
        self.best_moves = self.c4._get_better_move(self.current_player)
        self.move_played = move_played
        self.update_points()
        if self.verbose:
            print(self.best_moves)

        self.best_child = []

    def __str__(self):
        lines = [f"ARBRE {self.id} (Joueur: {self.current_player})"]
        child_ids = " ".join(str(child.id) for child in self.children)
        lines.append(child_ids)
        lines.append("-----------------------")
        return "\n".join(lines)

    def print_all_children(self, indent=0):
        """Affiche récursivement cet arbre et tous ses enfants avec une indentation."""
        prefix = "    " * indent
        print(f"{prefix}NOEUD {self.id} (Joueur: {self.current_player})")
        self.c4.print(self.c4.grid)
        print(f"{prefix}Mouvements: {self.best_moves}")
        print(f"{prefix}Points finaux : {self.points}")
        if self.best_child:
            best_ids = [child.id for child in self.best_child]
            print(f"{prefix}Meilleur(s) enfant(s) : {best_ids}")
        print(f"{prefix}-----------------------")

        for child in self.children:
            child.print_all_children(indent + 1)

    def list_brute_force(self):
        """Trouve tous les coups possibles depuis la grille de ce noeud."""
        brute_force = []
        rows = self.c4.row
        cols = self.c4.col

        for col in range(cols):
            for i in range(rows - 1, -1, -1):
                if self.c4.grid[i][col] == 0:
                    brute_force.append([[i, col]])
                    break

        return brute_force

    def build_tree(self, depth, current_id=2):
        if depth <= 0:
            return current_id

        brute_force = self.list_brute_force()

        for i in range(len(brute_force)):
            temp_c4 = copy.deepcopy(self.c4)
            r = brute_force[i][0][0]
            c = brute_force[i][0][1]

            temp_c4.grid[r][c] = self.current_player

            child = Tree(
                current_id,
                temp_c4,
                self,
                current_player=self.next_player_val,
                next_player_val=self.current_player,
                move_played=[r, c],
                verbose=self.verbose,
            )
            self.children.append(child)
            current_id += 1

        for child in self.children:
            current_id = child.build_tree(depth - 1, current_id)

        return current_id

    def update_points(self):
        if self.best_moves:
            best_key = max(self.best_moves, key=lambda k: self.best_moves[k][0])
            self.points += self.best_moves[best_key][0]

    def propagate_scores(self, ai_value=3):
        """
        Remonte récursivement les scores avec la logique Minimax.
        ai_value : La valeur du joueur qui est l'IA (celui qui veut maximiser).
        """
        if not self.children:
            return self.points

        for child in self.children:
            child.propagate_scores(ai_value)

        is_maximizing = self.current_player == ai_value

        best_score = -float("inf") if is_maximizing else float("inf")
        self.best_child = []

        for child in self.children:
            if is_maximizing:
                if child.points > best_score:
                    best_score = child.points
                    self.best_child = [child]
                elif child.points == best_score:
                    self.best_child.append(child)
            else:
                if child.points < best_score:
                    best_score = child.points
                    self.best_child = [child]
                elif child.points == best_score:
                    self.best_child.append(child)

        if best_score != -float("inf") and best_score != float("inf"):
            self.points += best_score

        return self.points


class Player:
    def __init__(self, name, value, shape):
        self.name = name
        self.value = value
        self.shape = shape

    def play_column(self, c4: Connect4, col: int):
        """Non-blocking server-safe move for a human player."""
        return c4.drop_token(col, self.value)

    def move(self, c4: Connect4):
        """Interactive CLI move wrapper."""
        while True:
            try:
                raw = input(f"{self.name} | Jouez : ")
                col = min(max(int(raw), 0), c4.col - 1)
                return self.play_column(c4, col)
            except (ValueError, IndexError):
                print("Coup invalide, veuillez rejouer")


class AI(Player):
    def __init__(self, name, value, shape, depth=2, level=None):
        super().__init__(name, value, shape)
        if level is not None and level in LEVEL_TO_DEPTH:
            self.level = level
            self.depth = LEVEL_TO_DEPTH[level]
        else:
            self.depth = depth
            self.level = DEPTH_TO_LEVEL.get(depth, "medium")

    @staticmethod
    def _format_heuristic_candidates(all_possible_moves):
        candidates = []
        for coord_str, payload in all_possible_moves.items():
            r_str, c_str = coord_str.split(":")
            reasons = payload[1] if isinstance(payload[1], list) else [str(payload[1])]
            candidates.append(
                {
                    "row": int(r_str),
                    "col": int(c_str),
                    "score": float(payload[0]),
                    "reasons": reasons,
                }
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates

    def _score_window(self, window, ai_val, opp_val, align):
        ai_cnt = window.count(ai_val)
        opp_cnt = window.count(opp_val)
        if ai_cnt > 0 and opp_cnt > 0:
            return 0
        if ai_cnt == align:
            return 10000
        if opp_cnt == align:
            return -10000
        if ai_cnt == align - 1 and opp_cnt == 0:
            return 55
        if opp_cnt == align - 1 and ai_cnt == 0:
            return -85
        if align >= 4:
            if ai_cnt == align - 2 and opp_cnt == 0:
                return 9
            if opp_cnt == align - 2 and ai_cnt == 0:
                return -12
        return 0

    def _evaluate_board(self, c4: Connect4, ai_val: int, opp_val: int) -> float:
        score = 0.0
        rows, cols, align = c4.row, c4.col, c4.align
        grid = c4.grid
        center = cols // 2

        # Center column control
        for r in range(rows):
            if grid[r][center] == ai_val:
                score += 4
            elif grid[r][center] == opp_val:
                score -= 4

        # Horizontal windows
        for r in range(rows):
            row_arr = grid[r]
            for c in range(cols - align + 1):
                score += self._score_window(row_arr[c : c + align], ai_val, opp_val, align)

        # Vertical windows
        for c in range(cols):
            for r in range(rows - align + 1):
                window = [grid[r + k][c] for k in range(align)]
                score += self._score_window(window, ai_val, opp_val, align)

        # Positive diagonals (\)
        for r in range(rows - align + 1):
            for c in range(cols - align + 1):
                window = [grid[r + k][c + k] for k in range(align)]
                score += self._score_window(window, ai_val, opp_val, align)

        # Negative diagonals (/)
        for r in range(align - 1, rows):
            for c in range(cols - align + 1):
                window = [grid[r - k][c + k] for k in range(align)]
                score += self._score_window(window, ai_val, opp_val, align)

        return score

    def _ordered_columns(self, c4: Connect4):
        center = (c4.col - 1) / 2.0
        return sorted(c4.get_valid_columns(), key=lambda c: abs(c - center))

    def _alphabeta_search(self, c4: Connect4, search_depth: int, start_time: float, heuristic_candidates: list):
        """
        True lookahead Alpha-Beta Minimax used for 'hard' and 'impossible' levels.
        Prevents the greedy heuristic traps that make weakc4 games end in 7 moves.
        """
        ai_val = self.value
        opp_val = c4.get_opponent(ai_val)
        ordered_cols = self._ordered_columns(c4)
        nodes = [0]

        # 1. Instant 1-ply win check
        for col in ordered_cols:
            r = c4.get_drop_row(col)
            c4.grid[r][col] = ai_val
            won = c4.has_win_at(r, col, ai_val)
            c4.grid[r][col] = 0
            if won:
                c4.grid[r][col] = ai_val
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "row": r,
                    "col": col,
                    "ai_info": {
                        "strategy": "minimax",
                        "level": self.level,
                        "depth": search_depth,
                        "elapsed_ms": elapsed_ms,
                        "chosen_score": 999999.0,
                        "heuristic_candidates": heuristic_candidates[:10],
                        "tree_info": {
                            "nodes_evaluated": 1,
                            "root_score": 999999.0,
                            "best_moves": [[r, col]],
                            "child_scores": [{"row": r, "col": col, "score": 999999.0}],
                        },
                    },
                }

        # 2. Instant 1-ply forced block check
        for col in ordered_cols:
            r = c4.get_drop_row(col)
            c4.grid[r][col] = opp_val
            opp_won = c4.has_win_at(r, col, opp_val)
            c4.grid[r][col] = 0
            if opp_won:
                c4.grid[r][col] = ai_val
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "row": r,
                    "col": col,
                    "ai_info": {
                        "strategy": "minimax",
                        "level": self.level,
                        "depth": search_depth,
                        "elapsed_ms": elapsed_ms,
                        "chosen_score": 999998.0,
                        "heuristic_candidates": heuristic_candidates[:10],
                        "tree_info": {
                            "nodes_evaluated": len(ordered_cols),
                            "root_score": 999998.0,
                            "best_moves": [[r, col]],
                            "child_scores": [{"row": r, "col": col, "score": 999998.0}],
                        },
                    },
                }

        def alphabeta(depth_left: int, alpha: float, beta: float, maximizing: bool) -> float:
            nodes[0] += 1
            valid = self._ordered_columns(c4)
            if not valid:
                return 0.0
            if depth_left == 0:
                return self._evaluate_board(c4, ai_val, opp_val)

            if maximizing:
                value = -float("inf")
                for col in valid:
                    r = c4.get_drop_row(col)
                    c4.grid[r][col] = ai_val
                    if c4.has_win_at(r, col, ai_val):
                        score = 100000.0 + depth_left * 100.0
                    else:
                        score = alphabeta(depth_left - 1, alpha, beta, False)
                    c4.grid[r][col] = 0
                    if score > value:
                        value = score
                    if value > alpha:
                        alpha = value
                    if alpha >= beta:
                        break
                return value
            else:
                value = float("inf")
                for col in valid:
                    r = c4.get_drop_row(col)
                    c4.grid[r][col] = opp_val
                    if c4.has_win_at(r, col, opp_val):
                        score = -100000.0 - depth_left * 100.0
                    else:
                        score = alphabeta(depth_left - 1, alpha, beta, True)
                    c4.grid[r][col] = 0
                    if score < value:
                        value = score
                    if value < beta:
                        beta = value
                    if alpha >= beta:
                        break
                return value

        child_scores = []
        best_score = -float("inf")
        best_moves = []
        alpha = -float("inf")
        beta = float("inf")
        eps = 1e-4

        for col in ordered_cols:
            r = c4.get_drop_row(col)
            c4.grid[r][col] = ai_val
            score = alphabeta(search_depth - 1, alpha, beta, False)
            c4.grid[r][col] = 0

            child_scores.append({"row": r, "col": col, "score": round(float(score), 1)})
            if score > best_score + eps:
                best_score = score
                best_moves = [[r, col]]
                # Keep alpha strictly below best_score so fail-low pruned blunders
                # can never tie with best_score and sneak into best_moves.
                alpha = best_score - eps
            elif abs(score - best_score) <= eps:
                best_moves.append([r, col])

        chosen_row, chosen_col = random.choice(best_moves)
        c4.grid[chosen_row][chosen_col] = ai_val
        child_scores.sort(key=lambda item: item["score"], reverse=True)
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "row": chosen_row,
            "col": chosen_col,
            "ai_info": {
                "strategy": "minimax",
                "level": self.level,
                "depth": search_depth,
                "elapsed_ms": elapsed_ms,
                "chosen_score": round(float(best_score), 1),
                "heuristic_candidates": heuristic_candidates[:8],
                "tree_info": {
                    "nodes_evaluated": nodes[0],
                    "root_score": round(float(best_score), 1),
                    "best_moves": best_moves,
                    "child_scores": child_scores,
                },
            },
        }

    def choose_move(self, c4: Connect4):
        """
        Non-blocking AI move selection mapped to difficulty levels:
        - easy (depth 1): WeakC4 heuristic with occasional relaxed moves + depth-1 Tree.
        - medium (depth 2): Classic WeakC4 heuristic-first + depth-2 Minimax Tree fallback.
        - hard (depth 3): True lookahead Alpha-Beta Minimax (ply 4, or 3 on wide boards).
        - impossible (depth 4): Deep Alpha-Beta Minimax (ply 6 on standard boards, 5 on wide).
        """
        start_time = time.perf_counter()
        valid_cols = c4.get_valid_columns()
        if not valid_cols:
            raise ValueError("No valid moves remaining on the board.")

        all_possible_moves = c4._get_better_move(self.value)
        heuristic_candidates = self._format_heuristic_candidates(all_possible_moves)

        # Hard & Impossible use true lookahead so they see forks and multi-ply traps
        if self.level == "hard":
            search_depth = 3 if c4.col >= 9 else 4
            return self._alphabeta_search(c4, search_depth, start_time, heuristic_candidates)
        if self.level == "impossible":
            if c4.col >= 10:
                search_depth = 4
            elif c4.col >= 8:
                search_depth = 5
            else:
                search_depth = 6
            return self._alphabeta_search(c4, search_depth, start_time, heuristic_candidates)

        # Easy & Medium preserve WeakC4's heuristic-first + Tree fallback flow
        if all_possible_moves:
            top_score = max(v[0] for v in all_possible_moves.values())
            # On Easy, still take immediate wins/blocks but occasionally explore other valid columns
            if self.level == "easy" and top_score < 999998 and random.random() < 0.35:
                col = random.choice(valid_cols)
                row, col = c4.drop_token(col, self.value)
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "row": row,
                    "col": col,
                    "ai_info": {
                        "strategy": "heuristic",
                        "level": self.level,
                        "depth": self.depth,
                        "elapsed_ms": elapsed_ms,
                        "chosen_score": 0.0,
                        "heuristic_candidates": heuristic_candidates[:10],
                        "tree_info": None,
                    },
                }

            top_keys = [k for k, v in all_possible_moves.items() if v[0] == top_score]
            best_move = random.choice(top_keys)
            row, col = int(best_move.split(":")[0]), int(best_move.split(":")[1])
            c4.grid[row][col] = self.value

            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "row": row,
                "col": col,
                "ai_info": {
                    "strategy": "heuristic",
                    "level": self.level,
                    "depth": self.depth,
                    "elapsed_ms": elapsed_ms,
                    "chosen_score": float(top_score),
                    "heuristic_candidates": heuristic_candidates[:10],
                    "tree_info": None,
                },
            }

        opponent = c4.get_opponent(self.value)
        root_c4 = copy.deepcopy(c4)
        root_c4.verbose = False
        root = Tree(
            1,
            root_c4,
            None,
            current_player=self.value,
            next_player_val=opponent,
            verbose=c4.verbose,
        )
        next_id = root.build_tree(self.depth)
        root_score = root.propagate_scores(ai_value=self.value)

        if root.best_child:
            chosen_child = random.choice(root.best_child)
            row, col = chosen_child.move_played
            if not c4.is_playable_cell(row, col):
                row, col = c4.drop_token(col, self.value)
            else:
                c4.grid[row][col] = self.value

            child_scores = [
                {
                    "row": ch.move_played[0],
                    "col": ch.move_played[1],
                    "score": float(ch.points),
                }
                for ch in root.children
                if ch.move_played is not None
            ]
            child_scores.sort(key=lambda item: item["score"], reverse=True)

            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "row": row,
                "col": col,
                "ai_info": {
                    "strategy": "tree",
                    "level": self.level,
                    "depth": self.depth,
                    "elapsed_ms": elapsed_ms,
                    "chosen_score": float(chosen_child.points),
                    "heuristic_candidates": [],
                    "tree_info": {
                        "nodes_evaluated": next_id - 1,
                        "root_score": float(root_score),
                        "best_moves": [ch.move_played for ch in root.best_child],
                        "child_scores": child_scores,
                    },
                },
            }

        center = (c4.col - 1) / 2.0
        col = min(valid_cols, key=lambda c: abs(c - center))
        row, col = c4.drop_token(col, self.value)
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "row": row,
            "col": col,
            "ai_info": {
                "strategy": "fallback",
                "level": self.level,
                "depth": self.depth,
                "elapsed_ms": elapsed_ms,
                "chosen_score": 0.0,
                "heuristic_candidates": [],
                "tree_info": None,
            },
        }

    def move(self, c4: Connect4):
        """Interactive CLI move wrapper (Press Enter for AI, or enter column index)."""
        while True:
            raw = input(f"{self.name} | Jouez : ")
            if raw == "":
                result = self.choose_move(c4)
                return result["row"], result["col"]
            try:
                col = min(max(int(raw), 0), c4.col - 1)
                return self.play_column(c4, col)
            except (ValueError, IndexError):
                print("Coup invalide, veuillez rejouer")


def init_players(players):
    return Player(*players[1]), Player(*players[2])


if __name__ == "__main__":
    cli_players = {
        3: ["AI1", 3, "◘", 2],
        4: ["AI2", 4, "•", 2],
    }

    game = Connect4(cli_players, 3, 7, 8, 4, verbose=True)
    ai1 = AI("AI1", 3, "◘", depth=3, level="hard")
    ai2 = AI("AI2", 4, "•", depth=3, level="hard")

    game.print()
    while True:
        game.current_player = ai1.value
        ai1.move(game)
        game.print()
        winner, cells = game.check_win()
        if winner or game.is_full():
            print("Game Over:", winner, cells)
            break

        game.current_player = ai2.value
        ai2.move(game)
        game.print()
        winner, cells = game.check_win()
        if winner or game.is_full():
            print("Game Over:", winner, cells)
            break
