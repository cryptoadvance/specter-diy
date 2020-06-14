import lvgl as lv
from .common import *
from .decorators import *
from .components import MnemonicTable, HintKeyboard
import rng
import asyncio

class Screen(lv.obj):
    network = 'test'
    COLORS = {
        'main': lv.color_hex(0xFF9A00),
        'test': lv.color_hex(0x00F100),
        'regtest': lv.color_hex(0x00CAF1),
        'signet': lv.color_hex(0xBD10E0),
    }
    def __init__(self):
        super().__init__()
        self.waiting = True
        self._value = None

        if type(self).network in type(self).COLORS:
            self.topbar = lv.obj(self)
            s = lv.style_t()
            lv.style_copy(s, styles["theme"].style.btn.rel)
            s.body.main_color = type(self).COLORS[type(self).network]
            s.body.grad_color = type(self).COLORS[type(self).network]
            s.body.opa = 200
            s.body.radius = 0
            s.body.border.width = 0
            self.topbar.set_style(s)
            self.topbar.set_size(HOR_RES, 5)
            self.topbar.set_pos(0, 0)

    def release(self):
        self.waiting = False

    def get_value(self):
        """
        Redefine this function to get value entered by the user
        """
        return self._value

    def set_value(self, value):
        self._value = value
        self.release()

    async def result(self):
        self.waiting = True
        while self.waiting:
            await asyncio.sleep_ms(1)
        return self.get_value()

class PinScreen(Screen):
    network = None
    def __init__(self, title="Enter your PIN code", note=None, get_word=None):
        super().__init__()
        self.title = add_label(title, scr=self, y=PADDING, style="title")
        if note is not None:
            lbl = add_label(note, scr=self, style="hint")
            lbl.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 180)
        self.get_word = get_word
        if get_word is not None:
            self.words = add_label(get_word(b""), scr=self)
            self.words.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 210)
        btnm = lv.btnm(self)
        # shuffle numbers to make sure 
        # no constant fingerprints left on screen
        buttons = ["%d" % i for i in range(0,10)]
        btnmap = []
        for j in range(3):
            for i in range(3):
                v = rng.get_random_bytes(1)[0] % len(buttons)
                btnmap.append(buttons.pop(v))
            btnmap.append("\n")
        btnmap = btnmap+[lv.SYMBOL.CLOSE, buttons.pop(), lv.SYMBOL.OK, ""]
        btnm.set_map(btnmap)
        btnm.set_width(HOR_RES)
        btnm.set_height(HOR_RES)
        btnm.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)
        # remove feedback on press to avoid sidechannels
        btnm.set_style(lv.btnm.STYLE.BTN_PR,btnm.get_style(lv.btnm.STYLE.BTN_REL))

        self.pin = lv.ta(self)
        self.pin.set_text("")
        self.pin.set_pwd_mode(True)
        style = lv.style_t()
        lv.style_copy(style, styles["theme"].style.ta.oneline)
        style.text.font = lv.font_roboto_28
        style.text.color = lv.color_hex(0xffffff)
        style.text.letter_space = 15
        self.pin.set_style(lv.label.STYLE.MAIN, style)
        self.pin.set_width(HOR_RES-2*PADDING)
        self.pin.set_x(PADDING)
        self.pin.set_y(PADDING+50)
        self.pin.set_cursor_type(lv.CURSOR.HIDDEN)
        self.pin.set_one_line(True)
        self.pin.set_text_align(lv.label.ALIGN.CENTER)
        self.pin.set_pwd_show_time(0)
        self.pin.align(btnm, lv.ALIGN.OUT_TOP_MID, 0, -150)

        btnm.set_event_cb(self.cb);

    def reset(self):
        self.pin.set_text("")
        if self.get_word is not None:
            self.words.set_text(self.get_word(b""))

    @feed_rng
    def cb(self, obj, event):
        if event == lv.EVENT.RELEASED:
            c = obj.get_active_btn_text()
            if c is None:
                return
            if c == lv.SYMBOL.CLOSE:
                self.reset()
            elif c == lv.SYMBOL.OK:
                self.release()
            else:
                self.pin.add_text(c)
                # add new anti-phishing word
                if self.get_word is not None:
                    cur_words = self.words.get_text()
                    cur_words += " "+self.get_word(self.pin.get_text())
                    self.words.set_text(cur_words)

    def get_value(self):
        return self.pin.get_text()

class DerivationScreen(Screen):
    PATH_CHARSET = [
        "1","2","3",lv.SYMBOL.LEFT,"\n",
        "4","5","6","h","\n",
        "7","8","9","/","\n",
        "Back", "0", lv.SYMBOL.CLOSE, lv.SYMBOL.OK,""
    ]
    def __init__(self, title="Enter derivation path"):
        super().__init__()
        self.title = add_label(title, scr=self, y=PADDING, style="title")
        self.kb = lv.btnm(self)
        self.kb.set_map(type(self).PATH_CHARSET)
        self.kb.set_width(HOR_RES)
        self.kb.set_height(VER_RES//2)
        self.kb.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

        lbl = add_label("m/", style="title", scr=self)
        lbl.set_y(PADDING+150)
        lbl.set_width(40)
        lbl.set_x(PADDING)

        self.ta = lv.ta(self)
        self.ta.set_text("")
        self.ta.set_width(HOR_RES-2*PADDING-40)
        self.ta.set_x(PADDING+40)
        self.ta.set_y(PADDING+150)
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
            self.set_value("m/"+self.ta.get_text())
            self.ta.set_text("")
        elif c[0] == "h":
            if last.isdigit():
                self.ta.add_text("h/")
        elif c[0] == "/":
            if last.isdigit() or last == "h":
                self.ta.add_text(c)
        else:
            self.ta.add_text(c)

class MenuScreen(Screen):
    def __init__(self, buttons=[], 
                 title="What do you want to do?", note=None,
                 y0=80, last=None
                 ):
        super().__init__()
        y = y0
        self.title = add_label(title, style="title", scr=self)
        if note is not None:
            self.note = add_label(note, style="hint", scr=self)
            self.note.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
            y += self.note.get_height()
        for value, text in buttons:
            if text is not None:
                if value is not None:
                    add_button(text, 
                        on_release(
                            cb_with_args(self.set_value, value)
                        ), y=y, scr=self)
                    y+=85
                else:
                    add_label(text.upper(), y=y+10, style="hint", scr=self)
                    y+=50
            else:
                y+=40
        if last is not None:
            self.add_back_button(*last)

    def add_back_button(self, value, text=None):
        if text is None:
            text = lv.SYMBOL.LEFT+" Back"
        add_button(text, 
                on_release(
                        cb_with_args(self.set_value, value)
                ), scr=self)

class Alert(Screen):
    def __init__(self, title, message, button_text=(lv.SYMBOL.LEFT+" Back")):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        self.page = lv.page(self)
        self.page.set_size(480, 600)
        self.message = add_label(message, scr=self.page)
        self.page.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)

        self.close_button = add_button(scr=self, 
                                callback=on_release(self.release))

        self.close_label = lv.label(self.close_button)
        self.close_label.set_text(button_text)

class Prompt(Screen):
    def __init__(self, title="Are you sure?", message="Make a choice"):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        self.page = lv.page(self)
        self.page.set_size(480, 600)
        self.message = add_label(message, scr=self.page)
        self.page.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)

        (self.cancel_button, 
         self.confirm_button) = add_button_pair(
                    "Cancel", on_release(cb_with_args(self.set_value,False)), 
                    "Confirm", on_release(cb_with_args(self.set_value,True)), 
                    scr=self)

class QRAlert(Alert):
    def __init__(self,
                 title="QR Alert!", 
                 message="Something happened", 
                 qr_message=None,
                 qr_width=None,
                 button_text="Close"):
        if qr_message is None:
            qr_message = message
        super().__init__(title, message, button_text)
        self.qr = add_qrcode(qr_message, scr=self, width=qr_width)
        self.qr.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)
        self.message.align(self.qr, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)

class XPubScreen(QRAlert):
    def __init__(self,
                 xpub,
                 slip132 = None,
                 prefix = None,
                 title="Your master public key", 
                 qr_width=None,
                 button_text="Close"):
        message = xpub
        if slip132 is not None:
            message = slip132
        if prefix is not None:
            message = prefix+message
        super().__init__(title, message, message)
        self.xpub = xpub
        self.prefix = prefix
        self.slip132 = slip132

        if prefix is not None:
            lbl = lv.label(self)
            lbl.set_text("Show derivation path")
            lbl.set_pos(2*PADDING, 540)
            self.prefix_switch = lv.sw(self)
            self.prefix_switch.on(lv.ANIM.OFF)
            self.prefix_switch.align(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

        if slip132 is not None:
            lbl = lv.label(self)
            lbl.set_text("Use SLIP-132")
            lbl.set_pos(2*PADDING, 590)
            self.slip_switch = lv.sw(self)
            self.slip_switch.on(lv.ANIM.OFF)
            self.slip_switch.align(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

        if prefix is not None:
            self.prefix_switch.set_event_cb(on_release(self.toggle_event))
        if slip132 is not None:
            self.slip_switch.set_event_cb(on_release(self.toggle_event))

    def toggle_event(self):
        msg = self.xpub
        if self.slip132 is not None and self.slip_switch.get_state():
            msg = self.slip132
        if self.prefix is not None and self.prefix_switch.get_state():
            msg = self.prefix+msg
        self.message.set_text(msg)
        self.qr.set_text(msg)

class MnemonicScreen(Screen):
    def __init__(self, mnemonic="", title="Your recovery phrase", note=None):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        if note is not None:
            lbl = add_label(note, scr=self, style="hint")
            lbl.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
        self.table = MnemonicTable(self)
        self.table.set_mnemonic(mnemonic)
        self.table.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        self.close_button = add_button(scr=self, 
                                callback=on_release(self.release))

        self.close_label = lv.label(self.close_button)
        self.close_label.set_text("OK")

class NewMnemonicScreen(MnemonicScreen):
    def __init__(self, generator, title="Your recovery phrase:", 
            note="Write it down and never show to anybody"):
        mnemonic = generator(12)
        super().__init__(mnemonic, title, note)
        self.table.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)

        self.close_label.set_text(lv.SYMBOL.LEFT+" Back")
        self.next_button = add_button(scr=self, 
                                callback=on_release(self.confirm))

        self.next_label = lv.label(self.next_button)
        self.next_label.set_text("Next "+lv.SYMBOL.RIGHT)
        align_button_pair(self.close_button, self.next_button)

        lbl = lv.label(self)
        lbl.set_text("Use 24 words")
        lbl.align(self.table, lv.ALIGN.OUT_BOTTOM_MID, 0, 60)
        lbl.set_x(120)

        self.switch = lv.sw(self)
        self.switch.off(lv.ANIM.OFF)
        self.switch.align(lbl, lv.ALIGN.OUT_RIGHT_MID, 20, 0)

        def cb():
            wordcount = 24 if self.switch.get_state() else 12
            self.table.set_mnemonic(generator(wordcount))

        self.switch.set_event_cb(on_release(cb))


    def confirm(self):
        self.set_value(self.table.get_mnemonic())

class RecoverMnemonicScreen(MnemonicScreen):
    def __init__(self, checker=None, lookup=None, 
                 title="Enter your recovery phrase"):
        super().__init__("", title)
        self.table.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        self.checker = checker
        self.lookup = lookup

        self.close_button.del_async()
        self.close_button = None
        self.kb = HintKeyboard(self)
        self.kb.set_map([
            "Q","W","E","R","T","Y","U","I","O","P","\n",
            "A","S","D","F","G","H","J","K","L","\n",
            "Z","X","C","V","B","N","M",lv.SYMBOL.LEFT,"\n",
            lv.SYMBOL.LEFT+" Back","Next word",lv.SYMBOL.OK+" Done",""
        ])

        if lookup is not None:
            # Next word button inactive
            self.kb.set_btn_ctrl(28, lv.btnm.CTRL.INACTIVE)
        if checker is not None:
            # Done inactive
            self.kb.set_btn_ctrl(29, lv.btnm.CTRL.INACTIVE)
        self.kb.set_width(HOR_RES)
        self.kb.set_height(VER_RES//3)
        self.kb.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)
        self.kb.set_event_cb(self.callback)

        if lookup is not None:
            self.autocomplete = lv.btnm(self)
            self.autocomplete.set_width(HOR_RES)
            self.autocomplete.set_height(50)
            self.autocomplete.align(self.kb, lv.ALIGN.OUT_TOP_MID, 0, 0)
            words = lookup("", 4)+[""]
            self.autocomplete.set_map(words)
            self.autocomplete.set_event_cb(self.select_word)

    def select_word(self, obj, event):
        if event != lv.EVENT.RELEASED:
            return
        word = obj.get_active_btn_text()
        if word is None:
            return
        self.table.autocomplete_word(word)
        self.autocomplete.set_map(self.lookup("", 4)+[""])
        self.check_buttons()

    def check_buttons(self):
        """
        Checks current mnemonic state and 
        disables / enables Next word and Done buttons
        """
        mnemonic = self.table.get_mnemonic()
        # check if we can autocomplete the last word
        if self.lookup is not None:
            self.kb.set_btn_ctrl(28, lv.btnm.CTRL.INACTIVE)
            word = self.table.get_last_word()
            candidates = self.lookup(word, 4)
            self.autocomplete.set_map(candidates+[""])
            if len(candidates) == 1 or word in candidates:
                self.kb.clear_btn_ctrl(28, lv.btnm.CTRL.INACTIVE)
                if len(candidates) == 1:
                    mnemonic = " ".join(self.table.words[:-1])
                    mnemonic += " "+candidates[0]
        mnemonic = mnemonic.strip()
        # check if mnemonic is valid
        if self.checker is not None and mnemonic is not None:
            if self.checker(mnemonic):
                self.kb.clear_btn_ctrl(29, lv.btnm.CTRL.INACTIVE)
            else:
                self.kb.set_btn_ctrl(29, lv.btnm.CTRL.INACTIVE)

    def callback(self, obj, event):
        if event != lv.EVENT.RELEASED:
            return
        c = obj.get_active_btn_text()
        if c is None:
            return
        num = obj.get_active_btn()
        # if inactive button is clicked - return
        if obj.get_btn_ctrl(num,lv.btnm.CTRL.INACTIVE):
            return
        if c == lv.SYMBOL.LEFT+" Back":
            self.set_value(None)
        elif c == lv.SYMBOL.LEFT:
            self.table.del_char()
        elif c == "Next word":
            word = self.table.get_last_word()
            if self.lookup is not None and len(word)>=2:
                candidates = self.lookup(word, 2)
                if len(candidates) == 1:
                    self.table.autocomplete_word(candidates[0])
        elif c == lv.SYMBOL.OK+" Done":
            pass
        else:
            self.table.add_char(c.lower())

        mnemonic = self.table.get_mnemonic()
        self.check_buttons()
        # if user was able to click this button then mnemonic is correct
        if c == lv.SYMBOL.OK+" Done":
            self.set_value(mnemonic)

class InputScreen(Screen):
    CHARSET = [
        "q","w","e","r","t","y","u","i","o","p","\n",
        "#@","a","s","d","f","g","h","j","k","l","\n",
        lv.SYMBOL.UP,"z","x","c","v","b","n","m",lv.SYMBOL.LEFT,"\n",
        lv.SYMBOL.CLOSE+" Clear"," ",lv.SYMBOL.OK+" Done",""
    ]
    CHARSET_EXTRA = [
        "1","2","3","4","5","6","7","8","9","0","\n",
        "aA","@","#","$","_","&","-","+","(",")","/","\n",
        "[","]","*","\"","'",":",";","!","?","\\",lv.SYMBOL.LEFT,"\n",
        lv.SYMBOL.CLOSE+" Clear"," ",lv.SYMBOL.OK+" Done",""
    ]
    def __init__(self, title="Enter your bip-39 password:", 
            note="It is never stored on the device"):
        super().__init__()
        self.kb = HintKeyboard(self)
        self.kb.set_map(type(self).CHARSET)
        self.kb.set_width(HOR_RES)
        self.kb.set_height(VER_RES//3)
        self.kb.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

        self.ta = lv.ta(self)
        self.ta.set_text("")
        # self.ta.set_pwd_mode(True)
        self.ta.set_width(HOR_RES-2*PADDING)
        self.ta.set_x(PADDING)
        self.ta.set_text_align(lv.label.ALIGN.CENTER)
        self.ta.set_y(PADDING+150)
        self.ta.set_cursor_type(lv.CURSOR.HIDDEN)
        self.ta.set_one_line(True)
        # self.ta.set_pwd_show_time(0)

        self.kb.set_event_cb(self.cb)

    def cb(self, obj, event):
        if event == lv.EVENT.RELEASED:
            c = obj.get_active_btn_text()
            if c is None:
                return
            if c[0] == lv.SYMBOL.LEFT:
                self.ta.del_char()
            elif c == lv.SYMBOL.UP or c == lv.SYMBOL.DOWN:
                for i,ch in enumerate(type(self).CHARSET):
                    if ch.isalpha():
                        if c == lv.SYMBOL.UP:
                            type(self).CHARSET[i] = type(self).CHARSET[i].upper()
                        else:
                            type(self).CHARSET[i] = type(self).CHARSET[i].lower()
                    elif ch == lv.SYMBOL.UP:
                        type(self).CHARSET[i] = lv.SYMBOL.DOWN
                    elif ch == lv.SYMBOL.DOWN:
                        type(self).CHARSET[i] = lv.SYMBOL.UP
                self.kb.set_map(type(self).CHARSET)
            elif c == "#@":
                self.kb.set_map(type(self).CHARSET_EXTRA)
            elif c == "aA":
                self.kb.set_map(type(self).CHARSET)
            elif c[0] == lv.SYMBOL.CLOSE:
                self.ta.set_text("")
            elif c[0] == lv.SYMBOL.OK:
                text = self.ta.get_text()
                self.ta.set_text("")
                self.set_value(text)
            else:
                self.ta.add_text(c)
