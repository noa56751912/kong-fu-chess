from dataclasses import dataclass

import cv2

BUTTON_BG = (70, 70, 70)          # BGR
BUTTON_BG_HOVER = (100, 100, 100)
BUTTON_BG_DISABLED = (50, 50, 50)
BUTTON_BORDER = (150, 150, 150)
BUTTON_TEXT = (255, 255, 255)
BUTTON_TEXT_DISABLED = (120, 120, 120)

INPUT_BG = (45, 45, 45)
INPUT_BG_FOCUSED = (60, 60, 60)
INPUT_BORDER = (120, 120, 120)
INPUT_BORDER_FOCUSED = (0, 215, 255)   # gold, matches ImageView's selection color
INPUT_TEXT = (255, 255, 255)


@dataclass
class Button:
    """A clickable rectangle drawn with plain cv2 primitives - the OpenCV-only
    stand-in for a GUI toolkit's button widget (per the project's no-other-
    GUI-library constraint)."""
    x: int
    y: int
    width: int
    height: int
    label: str
    enabled: bool = True

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height

    def draw(self, canvas, hovered: bool = False) -> None:
        if not self.enabled:
            bg, text_color = BUTTON_BG_DISABLED, BUTTON_TEXT_DISABLED
        else:
            bg, text_color = (BUTTON_BG_HOVER if hovered else BUTTON_BG), BUTTON_TEXT
        top_left, bottom_right = (self.x, self.y), (self.x + self.width, self.y + self.height)
        cv2.rectangle(canvas, top_left, bottom_right, bg, -1)
        cv2.rectangle(canvas, top_left, bottom_right, BUTTON_BORDER, 1)
        (text_w, text_h), _ = cv2.getTextSize(self.label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        text_x = self.x + (self.width - text_w) // 2
        text_y = self.y + (self.height + text_h) // 2
        cv2.putText(canvas, self.label, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    text_color, 2, cv2.LINE_AA)


class TextInputBox:
    """A single-line text box: renders its current text plus a caret, and
    accumulates typed characters from cv2.waitKey keycodes (append/backspace
    only - no cursor positioning or selection, which is all a room-id entry
    field needs). Relies on cv2.waitKey returning plain ASCII codes for
    printable characters when masked with 0xFF, which holds for ordinary
    alphanumeric input on this platform."""

    def __init__(self, x: int, y: int, width: int, height: int, max_length: int = 20):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.max_length = max_length
        self.text = ""
        self.focused = False

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height

    def handle_key(self, key: int) -> bool:
        """Returns True if the key was consumed. No-op (and returns False)
        while unfocused, so callers can dispatch a key to several widgets
        without needing to track focus themselves."""
        if not self.focused:
            return False
        if key in (8, 127):   # backspace / delete
            self.text = self.text[:-1]
            return True
        if key in (13, 10):   # enter - defocus, not itself a character
            self.focused = False
            return True
        if 32 <= key < 127 and len(self.text) < self.max_length:
            self.text += chr(key)
            return True
        return False

    def draw(self, canvas) -> None:
        bg = INPUT_BG_FOCUSED if self.focused else INPUT_BG
        border = INPUT_BORDER_FOCUSED if self.focused else INPUT_BORDER
        top_left, bottom_right = (self.x, self.y), (self.x + self.width, self.y + self.height)
        cv2.rectangle(canvas, top_left, bottom_right, bg, -1)
        cv2.rectangle(canvas, top_left, bottom_right, border, 1)
        display = self.text + ("_" if self.focused else "")
        cv2.putText(canvas, display, (self.x + 8, self.y + self.height - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, INPUT_TEXT, 1, cv2.LINE_AA)
