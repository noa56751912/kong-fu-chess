from typing import Iterable, Optional

import cv2
import numpy as np

from input.board_mapper import CELL_SIZE, cell_to_pixel
from model.board import Board
from model.move_record import MoveRecord
from model.piece import BLACK, WHITE
from model.position import Position
from realtime.motion import PendingMove, REST_DURATIONS
from rules.piece_config import JUMP, PIECE_CONFIG, StateConfig
from view.img import Img
from view.renderer import Renderer
from view.sprites import SpriteCache

LIGHT_SQUARE = (210, 238, 238)  # BGR
DARK_SQUARE = (86, 150, 118)  # BGR
SELECTION_COLOR = (0, 215, 255, 255)  # BGRA, gold
REST_FILL_COLOR = (60, 200, 255)  # BGR, amber
REST_FILL_ALPHA = 0.55

# Extra UI chrome around the board proper: a score strip above (black, who
# starts at the top of the board) and below (white), plus a move-log panel
# to the right. Kept as fixed pixel margins so board pixel space - and thus
# input/board_mapper's pixel_to_cell - stays untouched; only the *display*
# offset (see _board_origin) shifts where that space is painted.
TOP_MARGIN = 44
BOTTOM_MARGIN = 44
LOG_PANEL_WIDTH = 300
LOG_COLUMN_WIDTH = LOG_PANEL_WIDTH // 2
PANEL_BG = (40, 40, 40)  # BGR
TEXT_COLOR = (255, 255, 255, 255)  # BGRA
MAX_LOG_LINES = 20

# States whose sprite frames actually animate. Idle and move hold their first
# frame (idle sits still; move is already animated positionally by the board
# interpolation), but a jump stays on one cell for its whole airborne window,
# so without its own frame animation it would look frozen until it lands.
ANIMATED_STATES = set(REST_DURATIONS) | {JUMP}

WINDOW_NAME = "Image"  # matches Img.show()'s hardcoded title


class ImageView(Renderer):

    def __init__(self, cell_size: int = CELL_SIZE, sprite_cache: SpriteCache | None = None):
        self.cell_size = cell_size
        self.sprites = sprite_cache or SpriteCache(cell_size)
        self._background: Img | None = None
        # Piece.id -> (state, ms it was first observed in that state). Only
        # needed for states the engine doesn't itself timestamp (idle/jump/
        # rest); an in-flight move's own PendingMove.start_time is used
        # instead, since that's the authoritative source.
        self._state_entry: dict[int, tuple[str, int]] = {}
        # (scale, x_offset, y_offset) mapping board pixel space to the last
        # displayed window frame; identity until a window_size resize happens.
        self._display_transform: tuple[float, int, int] = (1.0, 0, 0)

    def _build_background(self, rows: int, cols: int) -> Img:
        # BGRA (not BGR): Img.draw_on() only alpha-blends a sprite when the
        # destination already has 4 channels: against a 3-channel canvas it
        # silently drops the sprite's alpha and pastes it opaquely instead.
        board_w, board_h = cols * self.cell_size, rows * self.cell_size
        width = board_w + LOG_PANEL_WIDTH
        height = TOP_MARGIN + board_h + BOTTOM_MARGIN
        canvas = np.empty((height, width, 4), dtype=np.uint8)
        canvas[..., 3] = 255
        canvas[..., :3] = PANEL_BG
        for row in range(rows):
            for col in range(cols):
                color = LIGHT_SQUARE if (row + col) % 2 == 0 else DARK_SQUARE
                x, y = col * self.cell_size, TOP_MARGIN + row * self.cell_size
                canvas[y:y + self.cell_size, x:x + self.cell_size, :3] = color
        background = Img()
        background.img = canvas
        return background

    def _ensure_background(self, board: Board) -> Img:
        if self._background is None:
            self._background = self._build_background(board.rows, board.cols)
        return self._background

    def _entry_time(self, piece, now_ms: int) -> int:
        prev = self._state_entry.get(piece.id)
        if prev is None or prev[0] != piece.state:
            self._state_entry[piece.id] = (piece.state, now_ms)
            return now_ms
        return prev[1]

    @staticmethod
    def _interpolated_pixel(move: PendingMove, now_ms: int, cell_size: int) -> tuple[int, int]:
        duration = move.arrive_time - move.start_time
        t = 0.0 if duration <= 0 else max(0.0, min(1.0, (now_ms - move.start_time) / duration))
        fx, fy = cell_to_pixel(move.frm, cell_size)
        tx, ty = cell_to_pixel(move.to, cell_size)
        return round(fx + (tx - fx) * t), round(fy + (ty - fy) * t)

    @staticmethod
    def _frame_index(config: StateConfig, state: str, elapsed_ms: int) -> int:
        if state not in ANIMATED_STATES:
            return 0
        count = len(config.frame_paths)
        idx = int(elapsed_ms / 1000 * config.frames_per_sec)
        return idx % count if config.is_loop else min(idx, count - 1)

    def _draw_selection(self, frame: Img, pos: Position) -> None:
        x, y = cell_to_pixel(pos, self.cell_size)
        y += TOP_MARGIN
        cv2.rectangle(frame.img, (x, y), (x + self.cell_size - 1, y + self.cell_size - 1),
                       SELECTION_COLOR, 3)

    def _draw_rest_fill(self, frame: Img, pos: Position, state: str, elapsed_ms: int) -> None:
        duration = REST_DURATIONS.get(state)
        if duration is None:
            return
        fraction = max(0.0, 1.0 - elapsed_ms / duration)
        if fraction <= 0.0:
            return
        x, y = cell_to_pixel(pos, self.cell_size)
        y += TOP_MARGIN
        height = round(self.cell_size * fraction)
        top = y + (self.cell_size - height)
        overlay = frame.img.copy()
        cv2.rectangle(overlay, (x, top), (x + self.cell_size - 1, y + self.cell_size - 1),
                       REST_FILL_COLOR, -1)
        cv2.addWeighted(overlay, REST_FILL_ALPHA, frame.img, 1 - REST_FILL_ALPHA, 0, frame.img)

    @staticmethod
    def _fit_to_window(image: np.ndarray, window_size: tuple[int, int]) -> tuple[np.ndarray, float, int, int]:
        """Scales `image` to fit inside `window_size`, letterboxed and centered.

        Returns the resulting image plus the (scale, x_offset, y_offset) used,
        so window-space coordinates (e.g. mouse clicks) can be mapped back.
        """
        win_w, win_h = window_size
        board_h, board_w = image.shape[:2]
        if win_w <= 0 or win_h <= 0 or board_w <= 0 or board_h <= 0:
            return image, 1.0, 0, 0
        scale = min(win_w / board_w, win_h / board_h)
        new_w, new_h = max(1, round(board_w * scale)), max(1, round(board_h * scale))
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        resized = cv2.resize(image, (new_w, new_h), interpolation=interpolation)
        canvas = np.zeros((win_h, win_w, image.shape[2]), dtype=image.dtype)
        x_off, y_off = (win_w - new_w) // 2, (win_h - new_h) // 2
        canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
        return canvas, scale, x_off, y_off

    def to_board_coords(self, x: int, y: int) -> tuple[int, int]:
        """Maps a point in the last displayed window frame back to board pixel space
        (i.e. what input/board_mapper.pixel_to_cell expects: (0, 0) at the board's
        own top-left, independent of the score/log chrome drawn around it)."""
        scale, x_off, y_off = self._display_transform
        bx, by = (x - x_off) / scale, (y - y_off) / scale
        return round(bx), round(by - TOP_MARGIN)

    @staticmethod
    def _pos_label(pos: Position, rows: int) -> str:
        """Algebraic-style label (e.g. 'e2'); row 0 is the top of the board (rank `rows`)."""
        return f"{chr(ord('a') + pos.col)}{rows - pos.row}"

    @staticmethod
    def _format_time(ms: int) -> str:
        # clock_ms is accumulated from float dt in gui_main's loop, so `ms`
        # can arrive as a float even though it's conceptually integer millis.
        total_seconds = int(max(0, ms) // 1000)
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    def _draw_score_bars(self, frame: Img, score: dict[str, int]) -> None:
        frame.put_text(f"Black: {score.get(BLACK, 0)}", 10, TOP_MARGIN - 14, 0.6, TEXT_COLOR, 2)
        bottom_y = frame.img.shape[0] - 14
        frame.put_text(f"White: {score.get(WHITE, 0)}", 10, bottom_y, 0.6, TEXT_COLOR, 2)

    def _draw_move_column(self, frame: Img, x: int, header: str, moves: list[MoveRecord], rows: int) -> None:
        y = TOP_MARGIN + 20
        frame.put_text(header, x, y, 0.55, TEXT_COLOR, 2)
        y += 26
        for record in moves[-MAX_LOG_LINES:]:
            line = (f"{record.kind} {self._pos_label(record.frm, rows)}"
                    f"-{self._pos_label(record.to, rows)}  {self._format_time(record.time_ms)}")
            frame.put_text(line, x, y, 0.42, TEXT_COLOR, 1)
            y += 20

    def _draw_move_log(self, frame: Img, board_w: int, rows: int, move_log: list[MoveRecord]) -> None:
        white_moves = [record for record in move_log if record.color == WHITE]
        black_moves = [record for record in move_log if record.color == BLACK]
        self._draw_move_column(frame, board_w + 8, "White", white_moves, rows)
        self._draw_move_column(frame, board_w + LOG_COLUMN_WIDTH + 4, "Black", black_moves, rows)

    def _draw_game_over(self, frame: Img, winner: Optional[str], score: dict[str, int]) -> None:
        h, w = frame.img.shape[:2]
        overlay = frame.img.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, frame.img, 0.45, 0, frame.img)

        label = "White wins!" if winner == WHITE else "Black wins!" if winner == BLACK else "Game Over"
        title = "Game Over" if winner is None else label
        white_line = f"White score: {score.get(WHITE, 0)}"
        black_line = f"Black score: {score.get(BLACK, 0)}"
        subtitle = "Press R to restart"

        def centered(text: str, y: int, font_size: float, thickness: int) -> None:
            (text_w, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_size, thickness)
            frame.put_text(text, (w - text_w) // 2, y, font_size, TEXT_COLOR, thickness)

        centered(title, h // 2 - 40, 1.0, 2)
        centered(white_line, h // 2, 0.7, 2)
        centered(black_line, h // 2 + 30, 0.7, 2)
        centered(subtitle, h // 2 + 70, 0.7, 2)

    def render(self, board: Board, now_ms: int, in_flight_moves: Iterable[PendingMove],
               selection: Optional[Position] = None,
               window_size: Optional[tuple[int, int]] = None,
               score: Optional[dict[str, int]] = None,
               move_log: Optional[list[MoveRecord]] = None,
               game_over: bool = False,
               winner: Optional[str] = None) -> None:
        background = self._ensure_background(board)
        frame = Img()
        frame.img = background.img.copy()

        moves_by_piece_id = {move.piece.id: move for move in in_flight_moves}
        for pos, piece in board:
            move = moves_by_piece_id.get(piece.id)
            if move is not None:
                x, y = self._interpolated_pixel(move, now_ms, self.cell_size)
                entry_time = move.start_time
            else:
                x, y = cell_to_pixel(pos, self.cell_size)
                entry_time = self._entry_time(piece, now_ms)
            y += TOP_MARGIN

            elapsed = max(0, now_ms - entry_time)
            self._draw_rest_fill(frame, pos, piece.state, elapsed)

            config = PIECE_CONFIG.get(piece.kind, piece.color, piece.state)
            frame_idx = self._frame_index(config, piece.state, elapsed)
            sprite = self.sprites.sprite(piece.kind, piece.color, piece.state, frame_idx)
            sprite.draw_on(frame, x, y)

        if selection is not None:
            self._draw_selection(frame, selection)

        score = score if score is not None else {}
        self._draw_score_bars(frame, score)
        self._draw_move_log(frame, board.cols * self.cell_size, board.rows, move_log or [])
        if game_over:
            self._draw_game_over(frame, winner, score)

        output = cv2.cvtColor(frame.img, cv2.COLOR_BGRA2BGR)
        if window_size is not None:
            output, scale, x_off, y_off = self._fit_to_window(output, window_size)
            self._display_transform = (scale, x_off, y_off)
        else:
            self._display_transform = (1.0, 0, 0)
        cv2.imshow(WINDOW_NAME, output)
