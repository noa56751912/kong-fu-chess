from model.position import Position


class TestEquality:

    def test_same_row_and_col_are_equal(self):
        assert Position(2, 3) == Position(2, 3)

    def test_different_row_are_not_equal(self):
        assert Position(2, 3) != Position(4, 3)

    def test_different_col_are_not_equal(self):
        assert Position(2, 3) != Position(2, 5)

    def test_hashable_for_dict_keys(self):
        assert Position(1, 1) in {Position(1, 1): "here"}


class TestReadableRepr:

    def test_repr_shows_row_and_col(self):
        assert repr(Position(2, 3)) == "Position(row=2, col=3)"

    def test_assertion_failure_message_is_readable(self):
        try:
            assert Position(1, 1) == Position(2, 2)
        except AssertionError as e:
            assert "Position(row=1, col=1)" in str(e)
            assert "Position(row=2, col=2)" in str(e)


class TestOffset:

    def test_offset_returns_new_position(self):
        assert Position(2, 3).offset(1, -1) == Position(3, 2)

    def test_offset_does_not_mutate_original(self):
        pos = Position(2, 3)
        pos.offset(1, 1)
        assert pos == Position(2, 3)
