import os
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

from weakc4 import DEPTH_TO_LEVEL, LEVEL_TO_DEPTH

MAX_AI_DEPTH = int(os.getenv("MAX_AI_DEPTH", "4"))
DifficultyLevel = Literal["easy", "medium", "hard", "impossible"]
GameMode = Literal["human_vs_ai", "player_vs_player", "ai_vs_ai"]
GameChannel = Literal["normal", "winaprize", "online_pvp"]


class GameConfig(BaseModel):
    rows: int = Field(default=6, ge=4, le=10, description="Number of board rows")
    cols: int = Field(default=7, ge=4, le=10, description="Number of board columns")
    align: int = Field(default=4, ge=3, le=10, description="Tokens required in a line to win")
    mode: GameMode = Field(default="human_vs_ai")
    starting_player: Literal[1, 2] = Field(default=1)
    human_player: Literal[1, 2] = Field(default=1)
    ai_level: Optional[DifficultyLevel] = Field(default=None)
    ai2_level: Optional[DifficultyLevel] = Field(default=None)
    ai_depth: Optional[int] = Field(default=None, ge=1, le=MAX_AI_DEPTH)
    ai2_depth: Optional[int] = Field(default=None, ge=1, le=MAX_AI_DEPTH)
    username: str = Field(default="Guest", max_length=32)
    player2_name: str = Field(default="Player 2", max_length=32)
    random_start: bool = Field(default=False)

    @model_validator(mode="after")
    def validate_config(self):
        max_align = min(self.rows, self.cols)
        if self.align > max_align:
            raise ValueError(
                f"align ({self.align}) cannot exceed min(rows, cols) ({max_align})."
            )

        self.username = (self.username or "Guest").strip()[:32] or "Guest"
        self.player2_name = (self.player2_name or "Player 2").strip()[:32] or "Player 2"

        if self.ai_level is not None:
            self.ai_depth = LEVEL_TO_DEPTH[self.ai_level]
        elif self.ai_depth is not None:
            self.ai_level = DEPTH_TO_LEVEL.get(self.ai_depth, "medium")
        else:
            self.ai_level = "medium"
            self.ai_depth = 2

        if self.ai2_level is not None:
            self.ai2_depth = LEVEL_TO_DEPTH[self.ai2_level]
        elif self.ai2_depth is not None:
            self.ai2_level = DEPTH_TO_LEVEL.get(self.ai2_depth, self.ai_level)
        else:
            self.ai2_level = self.ai_level
            self.ai2_depth = self.ai_depth

        return self


class CreateGameRequest(GameConfig):
    starting_player: Union[Literal[1, 2], Literal["random"]] = Field(default=1)
    auto_play_opening_ai: bool = Field(
        default=False,
        description="If true and AI moves first, automatically execute the opening AI move.",
    )


class ResetGameRequest(BaseModel):
    rows: Optional[int] = Field(default=None, ge=4, le=10)
    cols: Optional[int] = Field(default=None, ge=4, le=10)
    align: Optional[int] = Field(default=None, ge=3, le=10)
    mode: Optional[GameMode] = None
    starting_player: Optional[Union[Literal[1, 2], Literal["random"]]] = None
    human_player: Optional[Literal[1, 2]] = None
    ai_level: Optional[DifficultyLevel] = None
    ai2_level: Optional[DifficultyLevel] = None
    ai_depth: Optional[int] = Field(default=None, ge=1, le=MAX_AI_DEPTH)
    ai2_depth: Optional[int] = Field(default=None, ge=1, le=MAX_AI_DEPTH)
    username: Optional[str] = Field(default=None, max_length=32)
    player2_name: Optional[str] = Field(default=None, max_length=32)
    random_start: Optional[bool] = None
    auto_play_opening_ai: bool = False


class HumanMoveRequest(BaseModel):
    col: int = Field(..., ge=0, description="0-based column index to drop token into")
    auto_ai_reply: bool = Field(
        default=True,
        description="If true in human_vs_ai mode, immediately compute and apply the AI reply.",
    )


# --- Win a Prize ---


class WinAPrizeConfig(BaseModel):
    enabled: bool = True
    rows: int = Field(default=6, ge=4, le=10)
    cols: int = Field(default=7, ge=4, le=10)
    align: int = Field(default=4, ge=3, le=10)
    ai_level: DifficultyLevel = "medium"
    starting_player: Union[Literal[1, 2], Literal["random"]] = 1
    human_player: Literal[1, 2] = 1
    random_start: bool = False
    allow_undo: bool = False
    title: str = Field(default="Défi Puissance 4", max_length=80)
    subtitle: str = Field(default="Battez l'IA pour gagner un prix !", max_length=140)

    @model_validator(mode="after")
    def check_align(self):
        max_align = min(self.rows, self.cols)
        if self.align > max_align:
            raise ValueError(
                f"L'alignement ({self.align}) ne peut pas dépasser min(lignes, colonnes) ({max_align})."
            )
        if self.starting_player == "random":
            self.random_start = True
        return self


class UpdateWinAPrizeConfigRequest(WinAPrizeConfig):
    apply_to_live_games: bool = True


class CreatePrizeGameRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    auto_play_opening_ai: bool = False


# --- Online Friend Rooms (/game#XXXXXX) ---


class CreateRoomRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    rows: int = Field(default=6, ge=4, le=10)
    cols: int = Field(default=7, ge=4, le=10)
    align: int = Field(default=4, ge=3, le=10)
    starting_player: Union[Literal[1, 2], Literal["random"]] = 1
    random_start: bool = False

    @model_validator(mode="after")
    def check_align(self):
        max_align = min(self.rows, self.cols)
        if self.align > max_align:
            raise ValueError(f"align ({self.align}) cannot exceed min(rows, cols) ({max_align}).")
        return self


class JoinRoomRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)


class RoomMoveRequest(BaseModel):
    col: int = Field(..., ge=0)
    player_token: str = Field(..., min_length=1)


class RoomRematchRequest(BaseModel):
    player_token: str = Field(..., min_length=1)
    random_start: bool = False


# --- Admin ---


class AdminLoginRequest(BaseModel):
    password: str = Field(..., min_length=1)


class UpdateSessionDifficultyRequest(BaseModel):
    ai_level: DifficultyLevel
    ai2_level: Optional[DifficultyLevel] = None


class UpdateSessionLiveConfigRequest(BaseModel):
    ai_level: Optional[DifficultyLevel] = None
    ai2_level: Optional[DifficultyLevel] = None
    rows: Optional[int] = Field(default=None, ge=4, le=10)
    cols: Optional[int] = Field(default=None, ge=4, le=10)
    align: Optional[int] = Field(default=None, ge=3, le=10)
    allow_undo: Optional[bool] = None


class BlacklistEntryRequest(BaseModel):
    pattern: str = Field(..., min_length=1, max_length=32)
    match_type: Literal["exact", "contains"] = "exact"
    reason: str = Field(default="", max_length=120)


# --- Response Models ---


class PlayerInfo(BaseModel):
    id: Literal[1, 2]
    name: str
    type: Literal["human", "ai"]
    level: Optional[DifficultyLevel] = None
    depth: Optional[int] = None


class HeuristicCandidate(BaseModel):
    row: int
    col: int
    score: float
    reasons: list[str]


class TreeChildScore(BaseModel):
    row: int
    col: int
    score: float


class TreeInfo(BaseModel):
    nodes_evaluated: int
    root_score: float
    best_moves: list[list[int]]
    child_scores: list[TreeChildScore]


class AiInfo(BaseModel):
    strategy: Literal["heuristic", "tree", "minimax", "fallback"]
    level: DifficultyLevel = "medium"
    depth: int
    elapsed_ms: float
    chosen_score: float
    heuristic_candidates: list[HeuristicCandidate] = Field(default_factory=list)
    tree_info: Optional[TreeInfo] = None


class MoveRecord(BaseModel):
    ply: int
    player: Literal[1, 2]
    player_name: str
    player_type: Literal["human", "ai"]
    row: int
    col: int
    ai_info: Optional[AiInfo] = None


class GameStateResponse(BaseModel):
    session_id: str
    channel: GameChannel = "normal"
    room_code: Optional[str] = None
    waiting_for_opponent: bool = False
    allow_undo: bool = True
    username: str
    config: GameConfig
    players: dict[str, PlayerInfo]
    grid: list[list[int]]
    current_player: Literal[1, 2]
    valid_columns: list[int]
    status: Literal["playing", "win", "draw"]
    winner: Optional[Literal[1, 2]] = None
    winning_cells: list[list[int]] = Field(default_factory=list)
    last_move: Optional[MoveRecord] = None
    moves_applied: list[MoveRecord] = Field(default_factory=list)
    move_history: list[MoveRecord] = Field(default_factory=list)
    can_undo: bool = False
    ai_info: Optional[AiInfo] = None
    created_at: float
    updated_at: float


class RoomJoinResponse(BaseModel):
    room_code: str
    seat: Literal[0, 1, 2]
    player_token: Optional[str] = None
    game: GameStateResponse
