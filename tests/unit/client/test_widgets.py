import numpy as np

from client.widgets import Button, TextInputBox


class TestButtonContains:

    def test_point_inside_is_contained(self):
        button = Button(10, 10, 100, 40, "Play")
        assert button.contains(50, 30) is True

    def test_point_outside_is_not_contained(self):
        button = Button(10, 10, 100, 40, "Play")
        assert button.contains(200, 200) is False

    def test_point_on_edge_is_contained(self):
        button = Button(10, 10, 100, 40, "Play")
        assert button.contains(10, 10) is True
        assert button.contains(110, 50) is True

    def test_draw_does_not_raise(self):
        canvas = np.zeros((100, 200, 3), dtype=np.uint8)
        Button(10, 10, 100, 40, "Play").draw(canvas)


class TestTextInputBoxFocus:

    def test_unfocused_box_ignores_keys(self):
        box = TextInputBox(0, 0, 100, 30)
        assert box.handle_key(ord('a')) is False
        assert box.text == ""


class TestTextInputBoxTyping:

    def test_typing_appends_characters(self):
        box = TextInputBox(0, 0, 100, 30)
        box.focused = True
        for ch in "ab12":
            box.handle_key(ord(ch))
        assert box.text == "ab12"

    def test_backspace_removes_last_character(self):
        box = TextInputBox(0, 0, 100, 30)
        box.focused = True
        box.handle_key(ord('a'))
        box.handle_key(ord('b'))
        box.handle_key(8)
        assert box.text == "a"

    def test_backspace_on_empty_text_does_not_raise(self):
        box = TextInputBox(0, 0, 100, 30)
        box.focused = True
        box.handle_key(8)
        assert box.text == ""

    def test_enter_defocuses_without_adding_a_character(self):
        box = TextInputBox(0, 0, 100, 30)
        box.focused = True
        box.handle_key(ord('a'))
        box.handle_key(13)
        assert box.focused is False
        assert box.text == "a"

    def test_typing_beyond_max_length_is_ignored(self):
        box = TextInputBox(0, 0, 100, 30, max_length=3)
        box.focused = True
        for ch in "abcdef":
            box.handle_key(ord(ch))
        assert box.text == "abc"

    def test_non_printable_key_is_not_consumed(self):
        box = TextInputBox(0, 0, 100, 30)
        box.focused = True
        assert box.handle_key(1) is False
        assert box.text == ""

    def test_draw_does_not_raise(self):
        canvas = np.zeros((100, 200, 3), dtype=np.uint8)
        box = TextInputBox(0, 0, 100, 30)
        box.text = "abc123"
        box.focused = True
        box.draw(canvas)
