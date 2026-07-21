import pytest

from model.board import Board
from model.piece import BLACK, KING, ROOK, WHITE
from model.position import Position
from net.protocol import (
    ProtocolError, decode, deserialize_board, encode, format_move_string,
    position_to_square, serialize_board, square_to_position,
)


class TestSquareToPosition:

    def test_e2_on_standard_board(self):
        # rank 2, file e -> col 4; row = 8 - 2 = 6, matching STARTING_POSITION's
        # grid where row 6 holds the white pawns.
        assert square_to_position("e2", rows=8) == Position(6, 4)

    def test_a1_is_bottom_left(self):
        assert square_to_position("a1", rows=8) == Position(7, 0)

    def test_h8_is_top_right(self):
        assert square_to_position("h8", rows=8) == Position(0, 7)

    def test_invalid_square_raises_protocol_error(self):
        with pytest.raises(ProtocolError):
            square_to_position("zz", rows=8)


class TestPositionToSquare:

    def test_round_trips_with_square_to_position(self):
        for square in ("a1", "e2", "e4", "h8", "d5"):
            pos = square_to_position(square, rows=8)
            assert position_to_square(pos, rows=8) == square


class TestFormatMoveString:

    def test_matches_spec_example(self):
        frm = square_to_position("e2", rows=8)
        to = square_to_position("e5", rows=8)
        assert format_move_string("w", "Q", frm, to, rows=8) == "WQe2e5"


class TestEncodeDecode:

    def test_round_trip(self):
        message = {"type": "MOVE", "from": "e2", "to": "e4"}
        assert decode(encode(message)) == message

    def test_decode_invalid_json_raises_protocol_error(self):
        with pytest.raises(ProtocolError):
            decode("not json")

    def test_decode_without_type_field_raises_protocol_error(self):
        with pytest.raises(ProtocolError):
            decode(encode({"from": "e2"}))


class TestSerializeDeserializeBoard:

    def test_round_trip_preserves_real_piece_ids(self):
        # A grid-only round trip (board_parser.build_board) would renumber
        # ids by scan order - this must instead reproduce the exact ids
        # every EVENT's piece_id will keep referring to after a resync.
        board = Board(3, 3)
        rook = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        king = board.spawn_piece(BLACK, KING, Position(2, 2))
        rebuilt = deserialize_board(serialize_board(board))
        assert rebuilt.piece_at(Position(0, 0)).id == rook.id
        assert rebuilt.piece_at(Position(2, 2)).id == king.id

    def test_round_trip_preserves_mid_action_piece_state(self):
        board = Board(3, 3)
        rook = board.spawn_piece(WHITE, ROOK, Position(0, 0))
        rook.state = "long_rest"   # mid-cooldown, not idle
        rebuilt = deserialize_board(serialize_board(board))
        assert rebuilt.piece_at(Position(0, 0)).state == "long_rest"

    def test_round_trip_is_json_serializable(self):
        board = Board(2, 2)
        board.spawn_piece(WHITE, ROOK, Position(0, 0))
        assert decode(encode({"type": "SYNC_STATE", "board": serialize_board(board)}))
