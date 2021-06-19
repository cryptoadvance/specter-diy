"""
Screens where user needs to provide input, 
except mnemonics - they are in mnemonic.py
"""
import lvgl as lv
from ..common import *
from ..decorators import *
from ..components import HintKeyboard
from ..common import add_label
from .screen import Screen
import rng


class InputScreen(Screen):
    CHARSET = [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "0",
        "\n",
        "q",
        "w",
        "e",
        "r",
        "t",
        "y",
        "u",
        "i",
        "o",
        "p",
        "\n",
        "#@",
        "a",
        "s",
        "d",
        "f",
        "g",
        "h",
        "j",
        "k",
        "l",
        "\n",
        lv.SYMBOL.UP,
        "z",
        "x",
        "c",
        "v",
        "b",
        "n",
        "m",
        lv.SYMBOL.LEFT,
        "\n",
        lv.SYMBOL.LEFT + " Back",
        "[    space    ]",
        lv.SYMBOL.OK + " Done",
        "",
    ]
    CHARSET_EXTRA = [
        "!",
        "@",
        "#",
        "$",
        "%",
        "^",
        "&",
        "*",
        "(",
        ")",
        "\n",
        "~",
        "<",
        ">",
        "/",
        "\\",
        "{",
        "}",
        "[",
        "]",
        "\n",
        "aA",
        "\"",
        "'",
        "_",
        "-",
        "=",
        "+",
        "\n",
        "`",
        ":",
        ";",
        ",",
        ".",
        "|",
        "?",
        lv.SYMBOL.LEFT,
        "\n",
        lv.SYMBOL.LEFT + " Back",
        "[    space    ]",
        lv.SYMBOL.OK + " Done",
        "",
    ]

    def __init__(
            self,
            title="Enter your bip-39 password:",
            note="It is never stored on the device",
            suggestion="",
            min_length=0,
            max_length=None,
            strip=False,
    ):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        self.min_length = min_length
        self.max_length = max_length
        self.strip = strip

        if note is not None:
            self.note = add_label(note, scr=self, style="hint")
            self.note.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)

        self.kb = HintKeyboard(self)
        self.kb.set_map(self.CHARSET)
        self.kb.set_width(HOR_RES)
        self.kb.set_height(int(VER_RES / 2.5))
        self.kb.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

        self.ta = lv.ta(self)
        self.ta.set_text(suggestion)
        # self.ta.set_pwd_mode(True)
        self.ta.set_width(HOR_RES - 2 * PADDING)
        self.ta.set_x(PADDING)
        self.ta.set_text_align(lv.label.ALIGN.CENTER)
        self.ta.set_y(PADDING + 150)
        # self.ta.set_cursor_type(lv.CURSOR.HIDDEN)
        self.ta.set_one_line(True)
        # self.ta.set_pwd_show_time(0)

        self.kb.set_event_cb(self.cb)

        self.warning = add_label("", scr=self, style="hint")
        self.warning.align(self.ta, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

    def cb(self, obj, event):
        if event == lv.EVENT.RELEASED:
            c = obj.get_active_btn_text()
            if c is None:
                return
            if "space" in c:
                c = " "
            if c == lv.SYMBOL.LEFT:
                self.ta.del_char()
                self.check_text()
            elif c == lv.SYMBOL.UP or c == lv.SYMBOL.DOWN:
                for i, ch in enumerate(self.CHARSET):
                    if ch.isalpha():
                        if c == lv.SYMBOL.UP:
                            self.CHARSET[i] = self.CHARSET[i].upper()
                        else:
                            self.CHARSET[i] = self.CHARSET[i].lower()
                    elif ch == lv.SYMBOL.UP:
                        self.CHARSET[i] = lv.SYMBOL.DOWN
                    elif ch == lv.SYMBOL.DOWN:
                        self.CHARSET[i] = lv.SYMBOL.UP
                self.kb.set_map(self.CHARSET)
            elif c == "#@":
                self.kb.set_map(self.CHARSET_EXTRA)
            elif c == "aA":
                self.kb.set_map(self.CHARSET)
            elif c[0] == lv.SYMBOL.CLOSE:
                self.ta.set_text("")
            elif c[0] == lv.SYMBOL.OK:
                text = self.ta.get_text()
                if not self.check_text():
                    return
                self.ta.set_text("")
                if self.strip:
                    text = text.strip()
                self.set_value(text)
            elif c == lv.SYMBOL.LEFT + " Back":
                self.ta.set_text("")
                self.set_value(None)
            else:
                # check if input is empty:
                self.ta.add_text(c)
                self.check_text()

    def check_text(self):
        text = self.ta.get_text()
        if self.strip:
            text = text.strip()
        # check if input matches the limits
        if len(text) < self.min_length:
            self.warning.set_text("Enter at least %d%s character" % (self.min_length, " non-space" if self.strip else ""))
            return False
        if self.max_length and len(text) > self.max_length:
            self.warning.set_text("Value is too long! Must be between %d and %d characters" % (self.min_length, self.max_length))
            return False
        self.warning.set_text("")
        return True

class PinScreen(Screen):
    network = None
    CANCEL_VALUE = "*"

    def __init__(self, title="Enter your PIN code", note=None, get_word=None, subtitle=None, with_cancel=False):
        super().__init__()
        self.title = add_label(title, scr=self, y=PADDING, style="title")
        if subtitle is not None:
            lbl = add_label(subtitle, scr=self, style="hint")
            lbl.set_recolor(True)
            lbl.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        if note is not None:
            lbl = add_label(note, scr=self, style="hint")
            lbl.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 90)
        self.get_word = get_word
        if get_word is not None:
            self.words = add_label(get_word(b""), scr=self)
            self.words.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 120)
        btnm = lv.btnm(self)
        # shuffle numbers to make sure
        # no constant fingerprints left on screen
        buttons = ["%d" % i for i in range(0, 10)]
        btnmap = []
        for j in range(3):
            for i in range(3):
                v = rng.get_random_bytes(1)[0] % len(buttons)
                btnmap.append(buttons.pop(v))
            btnmap.append("\n")
        btnmap = btnmap + [lv.SYMBOL.CLOSE, buttons.pop(), " ", ""]
        btnm.set_map(btnmap)
        btnm.set_width(HOR_RES)
        btnm.set_height(HOR_RES)
        btnm.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, -100)
        # increase font size
        style = lv.style_t()
        lv.style_copy(style, btnm.get_style(lv.btnm.STYLE.BTN_REL))
        style.text.font = lv.font_roboto_28
        # remove feedback on press to avoid sidechannels
        btnm.set_style(lv.btnm.STYLE.BTN_REL, style)
        btnm.set_style(lv.btnm.STYLE.BTN_PR, style)

        self.pin = lv.ta(self)
        self.pin.set_text("")
        self.pin.set_pwd_mode(True)
        style = lv.style_t()
        lv.style_copy(style, styles["theme"].style.ta.oneline)
        style.text.font = lv.font_roboto_28
        style.text.color = styles["theme"].style.scr.text.color
        style.text.letter_space = 15
        self.pin.set_style(lv.label.STYLE.MAIN, style)
        self.pin.set_width(HOR_RES - 2 * PADDING)
        self.pin.set_x(PADDING)
        self.pin.set_y(PADDING + 50)
        self.pin.set_cursor_type(lv.CURSOR.HIDDEN)
        self.pin.set_one_line(True)
        self.pin.set_text_align(lv.label.ALIGN.CENTER)
        self.pin.set_pwd_show_time(0)
        self.pin.align(btnm, lv.ALIGN.OUT_TOP_MID, 0, -80)

        self.next_button = add_button(scr=self, callback=on_release(self.submit))

        self.next_label = lv.label(self.next_button)
        self.next_label.set_text("Next " + lv.SYMBOL.RIGHT)

        if with_cancel:
            self.cancel_button = add_button(scr=self, callback=on_release(self.cancel))

            self.cancel_label = lv.label(self.cancel_button)
            self.cancel_label.set_text(lv.SYMBOL.LEFT + " Cancel")

            align_button_pair(self.cancel_button, self.next_button)

        btnm.set_event_cb(feed_rng(self.cb))


    def reset(self):
        self.pin.set_text("")
        if self.get_word is not None:
            self.words.set_text(self.get_word(b""))

    def cb(self, obj, event):
        if event == lv.EVENT.RELEASED:
            c = obj.get_active_btn_text()
            if c is None or c == " ":
                return
            if c == lv.SYMBOL.CLOSE:
                self.reset()
            else:
                self.pin.add_text(c)
                # add new anti-phishing word
                if self.get_word is not None:
                    cur_words = self.words.get_text()
                    cur_words += " " + self.get_word(self.pin.get_text())
                    self.words.set_text(cur_words)

    def get_value(self):
        v = self.pin.get_text()
        return None if v == self.CANCEL_VALUE else v

    def submit(self):
        self.release()

    def cancel(self):
        # obj.del_async()
        self.pin.set_text(self.CANCEL_VALUE)
        self.release()

class DerivationScreen(Screen):
    PATH_CHARSET = [
        "1",
        "2",
        "3",
        lv.SYMBOL.LEFT,
        "\n",
        "4",
        "5",
        "6",
        "h",
        "\n",
        "7",
        "8",
        "9",
        "/",
        "\n",
        "Back",
        "0",
        lv.SYMBOL.CLOSE,
        lv.SYMBOL.OK,
        "",
    ]

    def __init__(self, title="Enter derivation path"):
        super().__init__()
        self.title = add_label(title, scr=self, y=PADDING, style="title")
        self.kb = lv.btnm(self)
        self.kb.set_map(self.PATH_CHARSET)
        self.kb.set_width(HOR_RES)
        self.kb.set_height(VER_RES // 2)
        self.kb.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

        lbl = add_label("m/", style="title", scr=self)
        lbl.set_y(PADDING + 150)
        lbl.set_width(40)
        lbl.set_x(PADDING)

        self.ta = lv.ta(self)
        self.ta.set_text("")
        self.ta.set_width(HOR_RES - 2 * PADDING - 40)
        self.ta.set_x(PADDING + 40)
        self.ta.set_y(PADDING + 150)
        self.ta.set_cursor_type(lv.CURSOR.HIDDEN)
        self.ta.set_one_line(True)

        self.kb.set_event_cb(self.cb)

    def cb(self, obj, event):
        if event != lv.EVENT.RELEASED:
            return
        c = obj.get_active_btn_text()
        if c is None:
            return
        der = self.ta.get_text()
        if len(der) == 0:
            last = "/"
        else:
            last = der[-1]
        if c == "Back":
            self.ta.set_text("")
            self.set_value(None)
        if c[0] == lv.SYMBOL.LEFT:
            self.ta.del_char()
        elif c[0] == lv.SYMBOL.CLOSE:
            self.ta.set_text("")
        elif c[0] == lv.SYMBOL.OK:
            self.set_value("m/" + self.ta.get_text())
            self.ta.set_text("")
        elif c[0] == "h":
            if last.isdigit():
                self.ta.add_text("h/")
        elif c[0] == "/":
            if last.isdigit() or last == "h":
                self.ta.add_text(c)
        else:
            self.ta.add_text(c)


class NumericScreen(Screen):
    NUMERIC_CHARSET = [
        "1",
        "2",
        "3",
        "\n",
        "4",
        "5",
        "6",
        "\n",
        "7",
        "8",
        "9",
        "\n",
        lv.SYMBOL.LEFT,
        "0",
        lv.SYMBOL.OK,
        "",
    ]

    def __init__(
            self,
            title="Enter account number",
            current_val='0'
    ):
        super().__init__()
        self.title = add_label(title, scr=self, y=PADDING, style="title")

        self.note = add_label("Current account number: %s" % current_val, scr=self, style="hint")
        self.note.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)

        self.kb = lv.btnm(self)
        self.kb.set_map(self.NUMERIC_CHARSET)
        self.kb.set_width(HOR_RES)
        self.kb.set_height(VER_RES // 2)
        self.kb.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

        lbl = add_label('', style="title", scr=self)
        lbl.set_y(PADDING + 150)
        lbl.set_width(40)
        lbl.set_x(PADDING)

        self.ta = lv.ta(self)
        self.ta.set_text("")
        self.ta.set_width(HOR_RES - 2 * PADDING - 40)
        self.ta.set_x(PADDING + 40)
        self.ta.set_y(PADDING + 150)
        self.ta.set_cursor_type(lv.CURSOR.HIDDEN)
        self.ta.set_one_line(True)
        self.kb.set_event_cb(self.cb)

    def cb(self, obj, event):
        if event != lv.EVENT.RELEASED:
            return
        c = obj.get_active_btn_text()
        if c is None:
            return
        account = self.ta.get_text()
        if len(account) == 0:
            last = '0'
        else:
            last = account[-1]
        if c[0] == lv.SYMBOL.LEFT:
            self.ta.del_char()
        elif c[0] == lv.SYMBOL.OK:
            self.set_value(self.ta.get_text())
            self.ta.set_text("")
        else:
            self.ta.add_text(c)
