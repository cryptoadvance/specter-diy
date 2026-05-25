import lvgl as lv
from .theme import styles


class MnemonicTable(lv.table):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.words = [""]
        self.callback = None
        # styles
        self.add_style(styles["page"], lv.PART.MAIN)
        self.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        cell_style = lv.style_t()
        cell_style.init()
        cell_style.set_bg_opa(0)
        cell_style.set_border_width(0)
        cell_style.set_pad_all(0)
        cell_style.set_pad_top(6)
        cell_style.set_pad_bottom(6)
        cell_style.set_text_font(lv.font_montserrat_22)
        cell_style.set_text_color(styles["ctxt"])
        self.cell_style = cell_style

        self.set_column_count(4)
        self.set_row_count(12)
        self.set_column_width(0, 40)
        self.set_column_width(2, 40)
        self.set_column_width(1, 180)
        self.set_column_width(3, 180)

        self.add_style(self.cell_style, lv.PART.ITEMS)
        self.add_event_cb(self._event_cb, lv.EVENT.ALL, None)
        self.add_event_cb(self._draw_event_cb, lv.EVENT.DRAW_TASK_ADDED, None)
        self.add_flag(lv.obj.FLAG.SEND_DRAW_TASK_EVENTS)

        for i in range(12):
            self.set_cell_value(i, 0, "%d" % (i + 1))
            self.set_cell_value(i, 2, "%d" % (i + 13))

    def set_event_cb(self, callback):
        self.callback = callback

    def set_click(self, enabled):
        if enabled:
            self.add_flag(lv.obj.FLAG.CLICKABLE)
        else:
            self.remove_flag(lv.obj.FLAG.CLICKABLE)

    def _event_cb(self, event):
        code = event.get_code()
        if code == lv.EVENT.DRAW_TASK_ADDED:
            return
        if self.callback is not None:
            self.callback(self, code)

    def _draw_event_cb(self, event):
        draw_task = event.get_draw_task()
        if draw_task.get_type() != lv.DRAW_TASK_TYPE.LABEL:
            return
        label_dsc = draw_task.get_label_dsc()
        if label_dsc is None:
            return
        if label_dsc.base.part == lv.PART.ITEMS and label_dsc.base.id2 in (0, 2):
            label_dsc.color = styles["chint"]

    def set_mnemonic(self, mnemonic: str):
        self.words = mnemonic.split()
        self.update()

    def update(self):
        for i in range(24):
            row = i % 12
            col = 1 + 2 * (i // 12)
            if i < len(self.words):
                self.set_cell_value(row, col, self.words[i])
            else:
                self.set_cell_value(row, col, "")

    def get_mnemonic(self) -> str:
        return " ".join(self.words)

    def get_last_word(self) -> str:
        if len(self.words) == 0:
            return ""
        else:
            return self.words[-1]

    def del_char(self):
        if len(self.words) == 0:
            return
        if len(self.words[-1]) == 0:
            self.words = self.words[:-1]
        else:
            self.words[-1] = self.words[-1][:-1]
        self.update()

    def autocomplete_word(self, word):
        if len(self.words) > 24:
            return
        if len(self.words) == 0:
            self.words.append(word)
        else:
            self.words[-1] = word
        if len(self.words) < 24:
            self.words.append("")
        self.update()

    def add_char(self, c):
        if len(self.words) > 24:
            return
        if len(self.words) == 0:
            self.words.append(c)
        else:
            self.words[-1] += c
        self.update()
