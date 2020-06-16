"""Mnemonic-related screens"""
import lvgl as lv
from ..common import *
from ..decorators import *
from ..components import MnemonicTable, HintKeyboard
from .screen import Screen

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

