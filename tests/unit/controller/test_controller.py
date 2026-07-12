from boardio.board_parser import build_board
from engine.game_engine import GameEngine
from input.controller import Controller
from model.position import Position


def make_controller(rows):
    grid = [row.split() for row in rows]
    engine = GameEngine(build_board(grid))
    return engine, Controller(engine)


class TestControllerClick:

    def test_click_selects_piece_at_pixel(self):
        engine, controller = make_controller(["wK . .", ". . .", ". . ."])
        controller.click(50, 50)
        assert engine.state.selection == Position(0, 0)

    def test_click_out_of_bounds_is_relayed_as_none(self):
        engine, controller = make_controller(["wK . .", ". . .", ". . ."])
        controller.click(50, 50)
        assert engine.state.selection == Position(0, 0)
        controller.click(9999, 9999)
        assert engine.state.selection is None


class TestControllerJump:

    def test_jump_schedules_jump_at_pixel(self):
        engine, controller = make_controller(["wK . .", ". . .", ". . ."])
        controller.jump(50, 50)
        assert engine.arbiter.is_busy(Position(0, 0))

    def test_jump_out_of_bounds_is_a_no_op(self):
        engine, controller = make_controller(["wK . .", ". . .", ". . ."])
        controller.jump(9999, 9999)
        assert engine.arbiter.status == {}
