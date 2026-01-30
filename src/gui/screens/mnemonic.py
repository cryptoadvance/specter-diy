"""Mnemonic-related screens"""
import lvgl as lv
from ..common import *
from ..decorators import *
from ..components import MnemonicTable, HintKeyboard
from .screen import Screen
from .prompt import Prompt

class MnemonicScreen(Screen):
    QR = 1
    SD = 2
    def __init__(self, mnemonic="", title="Your recovery phrase:", note=None):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        if note is not None:
            lbl = add_label(note, scr=self, style="hint")
            lbl.align_to(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
        self.table = MnemonicTable(self)
        self.table.set_mnemonic(mnemonic)
        self.table.align_to(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        self.close_button = add_button(scr=self, callback=on_release(self.release))

        self.close_label = lv.label(self.close_button)
        self.close_label.set_text("OK")

class MnemonicPrompt(Prompt):
    def __init__(self, mnemonic="", title="Your recovery phrase:", note=None):
        super().__init__(title, message="", note=note)
        table = MnemonicTable(self)
        table.set_mnemonic(mnemonic)
        table.align_to(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)


class ExportMnemonicScreen(MnemonicScreen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_qr_btn = add_button(text="Show as QR code", scr=self, callback=on_release(self.select_qr))
        self.show_qr_btn.align_to(self.table, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        self.save_sd_btn = add_button(text="Save to SD card (plaintext)", scr=self, callback=on_release(self.select_sd))
        self.save_sd_btn.align_to(self.show_qr_btn, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

    def select_sd(self):
        self.set_value(self.SD)

    def select_qr(self):
        self.set_value(self.QR)

class NewMnemonicScreen(MnemonicScreen):
    def __init__(
        self,
        generator,
        wordlist,
        fixer,
        title="Your recovery phrase:",
        note="Write it down and never show it to anybody.",
    ):
        self.fixer = fixer
        self.wordlist = wordlist
        mnemonic = generator(12)
        super().__init__(mnemonic, title, note)
        self.table.align_to(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)
        self.table.add_event_cb(self.on_word_click, lv.EVENT.ALL, None)
        # enable callbacks
        self.table.add_flag(lv.obj.FLAG.CLICKABLE)

        self.close_label.set_text(lv.SYMBOL.LEFT + " Back")
        self.done_button = add_button(scr=self, callback=on_release(self.confirm))

        self.done_label = lv.label(self.done_button)
        self.done_label.set_text(lv.SYMBOL.OK + " Done")
        align_button_pair(self.close_button, self.done_button)

        # toggle switch 12-24 words
        lbl = lv.label(self)
        lbl.set_text("Use 24 words")
        lbl.align_to(self.table, lv.ALIGN.OUT_BOTTOM_MID, 0, 40)
        lbl.set_x(120)
        self.switch_lbl = lbl

        self.switch = lv.switch(self)
        self.switch.remove_state(lv.STATE.CHECKED)  # Start in off state
        self.switch.align_to(lbl, lv.ALIGN.OUT_RIGHT_MID, 20, 0)

        def cb(e):
            wordcount = 24 if self.switch.has_state(lv.STATE.CHECKED) else 12
            self.table.set_mnemonic(generator(wordcount))

        self.switch.add_event_cb(cb, lv.EVENT.VALUE_CHANGED, None)

        # fix mnemonic components
        self.kb = lv.buttonmatrix(self)
        self.kb.set_map(["1", "2", "4", "8", "16", "32", "\n",
                         "64", "128", "256", "512", "1024", ""])
        self.kb.set_ctrl_map([lv.buttonmatrix.CTRL.CHECKABLE for i in range(11)])
        self.kb.set_width(HOR_RES)
        self.kb.set_height(100)
        self.kb.align_to(self.table, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
        self.kb.add_flag(lv.obj.FLAG.HIDDEN)

        self.instruction = add_label("Hint: click on any word above to edit it.", scr=self, style="hint")
        self.instruction.align_to(self.kb, lv.ALIGN.OUT_BOTTOM_MID, 0, 15)


    def on_word_click(self, event):
        code = event.get_code()
        if code != lv.EVENT.RELEASED:
            return
        obj = event.get_target()
        # get coordinates
        indev = lv.indev_active()
        point = indev.get_point()
        # get offsets
        dx = point.x - obj.get_x()
        dy = point.y - obj.get_y()
        # get index
        idx = 12*int(dx > obj.get_width()//2) + int(12*dy/obj.get_height())
        self.change_word(idx)

    def change_word(self, idx):
        if idx >= len(self.table.words):
            return
        word = self.table.words[idx]
        self.instruction.set_text(
            "Changing word number %d:\n%s (%d in wordlist)"
            % (idx+1, word.upper(), self.wordlist.index(word)+1)
        )
        # hide switch
        if not self.switch.has_flag(lv.obj.FLAG.HIDDEN):
            self.switch.add_flag(lv.obj.FLAG.HIDDEN)
            self.switch_lbl.add_flag(lv.obj.FLAG.HIDDEN)
        self.kb.remove_flag(lv.obj.FLAG.HIDDEN)
        word_idx = self.wordlist.index(word)
        self.kb.set_ctrl_map([
            lv.buttonmatrix.CTRL.CHECKABLE | (lv.buttonmatrix.CTRL.CHECKED if ((word_idx>>i)&1) else 0)
            for i in range(11)
        ])
        # callback on toggle
        def cb(event):
            code = event.get_code()
            if code != lv.EVENT.RELEASED:
                return
            btn_id = self.kb.get_selected_button()
            c = self.kb.get_button_text(btn_id)
            if c is None:
                return
            bits = [self.kb.has_button_ctrl(i, lv.buttonmatrix.CTRL.CHECKED) for i in range(11)]
            num = 0
            for i, bit in enumerate(reversed(bits)):
                num = num << 1
                if bit:
                    num += 1
            # change word
            word = self.wordlist[num]
            self.table.words[idx] = word
            # fix mnemonic
            mnemonic = " ".join(self.table.words)
            self.table.set_mnemonic(self.fixer(mnemonic))
            self.instruction.set_text(
                "Changing word number %d:\n%s (%d in wordlist)"
                % (idx+1, word.upper(), self.wordlist.index(word)+1)
            )
        self.kb.add_event_cb(cb, lv.EVENT.ALL, None)


    def confirm(self):
        self.set_value(self.table.get_mnemonic())


class RecoverMnemonicScreen(MnemonicScreen):
    # button indexes
    BTN_NEXT = 28
    BTN_DONE = 29

    def __init__(
        self, checker=None, lookup=None, fixer=None, title="Enter your recovery phrase"
    ):
        super().__init__("", title)
        self.table.align_to(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        self.checker = checker
        self.lookup = lookup

        self.close_button.delete()
        self.close_button = None

        if lookup is not None:
            self.autocomplete = lv.buttonmatrix(self)

        self.kb = HintKeyboard(self)
        self.kb.set_map(
            [
                "Q",
                "W",
                "E",
                "R",
                "T",
                "Y",
                "U",
                "I",
                "O",
                "P",
                "\n",
                "A",
                "S",
                "D",
                "F",
                "G",
                "H",
                "J",
                "K",
                "L",
                "\n",
                "Z",
                "X",
                "C",
                "V",
                "B",
                "N",
                "M",
                lv.SYMBOL.LEFT,
                "\n",
                lv.SYMBOL.LEFT + " Back",
                "Next word",
                lv.SYMBOL.OK + " Done",
                "",
            ]
        )

        if lookup is not None:
            # Next word button inactive
            self.kb.set_button_ctrl(self.BTN_NEXT, lv.buttonmatrix.CTRL.DISABLED)
        if checker is not None:
            # Done inactive
            self.kb.set_button_ctrl(self.BTN_DONE, lv.buttonmatrix.CTRL.DISABLED)
        self.kb.set_width(HOR_RES)
        self.kb.set_height(260)
        self.kb.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.kb.set_event_cb(self.callback)

        self.fixer = fixer
        if fixer is not None:
            self.fix_button = add_button("fix", on_release(self.fix_cb), self)
            self.fix_button.set_size(55, 30)
            # position it out of the screen but on correct y
            self.fix_button.align_to(self.table, lv.ALIGN.OUT_BOTTOM_MID, -400, -38)

        if lookup is not None:
            self.autocomplete.set_width(HOR_RES)
            self.autocomplete.set_height(50)
            self.autocomplete.align_to(self.kb, lv.ALIGN.OUT_TOP_MID, 0, 0)
            words = lookup("", 4) + [""]
            self.autocomplete.set_map(words)
            self.autocomplete.add_event_cb(self.select_word, lv.EVENT.ALL, None)

    def fix_cb(self):
        self.table.set_mnemonic(self.fixer(self.get_mnemonic()))
        self.check_buttons()

    def select_word(self, event):
        code = event.get_code()
        if code != lv.EVENT.RELEASED:
            return
        btn_id = self.autocomplete.get_selected_button()
        word = self.autocomplete.get_button_text(btn_id)
        if word is None:
            return
        self.table.autocomplete_word(word)
        self.autocomplete.set_map(self.lookup("", 4) + [""])
        self.check_buttons()

    def get_mnemonic(self):
        mnemonic = self.table.get_mnemonic()
        # check if we can autocomplete the last word
        if self.lookup is not None:
            self.kb.set_button_ctrl(self.BTN_NEXT, lv.buttonmatrix.CTRL.DISABLED)
            word = self.table.get_last_word()
            candidates = self.lookup(word, 4)
            self.autocomplete.set_map(candidates + [""])
            if len(candidates) == 1 or word in candidates:
                self.kb.clear_button_ctrl(self.BTN_NEXT, lv.buttonmatrix.CTRL.DISABLED)
                if len(candidates) == 1:
                    mnemonic = " ".join(self.table.words[:-1])
                    mnemonic += " " + candidates[0]
        return mnemonic.strip()

    def check_buttons(self):
        """
        Checks current mnemonic state and
        disables / enables Next word and Done buttons
        """
        mnemonic = self.get_mnemonic()
        # check if mnemonic is valid
        if self.checker is not None and mnemonic is not None:
            if self.checker(mnemonic):
                self.kb.clear_button_ctrl(self.BTN_DONE, lv.buttonmatrix.CTRL.DISABLED)
            else:
                self.kb.set_button_ctrl(self.BTN_DONE, lv.buttonmatrix.CTRL.DISABLED)
            # check if we are at 12, 18 or 24 words
            # offer to fix mnemonic if it's invalid
            num_words = len(mnemonic.split())
            if (
                self.fixer is not None
                and num_words in [12, 18, 24]
                and self.kb.has_button_ctrl(self.BTN_DONE, lv.buttonmatrix.CTRL.DISABLED)
            ):
                # set correct button coordinates
                y = -33 - self.table.get_height() // 2 if num_words == 18 else -38
                x = -40 if num_words == 12 else -40 + self.table.get_width() // 2
                # check if we can fix the mnemonic
                try:
                    self.fixer(mnemonic)
                    self.fix_button.align_to(self.table, lv.ALIGN.OUT_BOTTOM_MID, x, y)
                except:
                    self.fix_button.align_to(
                        self.table, lv.ALIGN.OUT_BOTTOM_MID, -400, -38
                    )
            else:
                self.fix_button.align_to(self.table, lv.ALIGN.OUT_BOTTOM_MID, -400, -38)

    def callback(self, obj, event):
        if event != lv.EVENT.RELEASED:
            return
        num = obj.get_selected_button()
        c = obj.get_button_text(num)
        if c is None:
            return
        # if inactive button is clicked - return
        if obj.has_button_ctrl(num, lv.buttonmatrix.CTRL.DISABLED):
            return
        if c == lv.SYMBOL.LEFT + " Back":
            self.confirm_exit()
        elif c == lv.SYMBOL.LEFT:
            self.table.del_char()
        elif c == "Next word":
            word = self.table.get_last_word()
            if self.lookup is not None and len(word) >= 2:
                candidates = self.lookup(word, 2)
                if len(candidates) == 1:
                    self.table.autocomplete_word(candidates[0])
        elif c == lv.SYMBOL.OK + " Done":
            pass
        else:
            self.table.add_char(c.lower())

        mnemonic = self.get_mnemonic()
        self.check_buttons()
        # if user was able to click this button then mnemonic is correct
        if c == lv.SYMBOL.OK + " Done":
            self.set_value(mnemonic)

    def confirm_exit(self):

        mnemonic = self.table.get_mnemonic()
        if len(mnemonic) == 0:
            self.set_value(None)
            return

        # LVGL 9.x msgbox with backdrop (pass None for modal)
        mbox = lv.msgbox(None)
        mbox.add_title("Confirm Exit")
        mbox.add_text(
            "Are you sure you want to exit?\n\n"
            "Everything you entered will be forgotten!"
        )

        btn_stay = mbox.add_footer_button("No, stay here")
        btn_leave = mbox.add_footer_button("Yes, leave")

        def on_stay(e):
            lv.msgbox.close(mbox)

        def on_leave(e):
            lv.msgbox.close(mbox)
            self.set_value(None)

        btn_stay.add_event_cb(on_stay, lv.EVENT.CLICKED, None)
        btn_leave.add_event_cb(on_leave, lv.EVENT.CLICKED, None)
