import lvgl as lv
from .theme import styles


class MnemonicTable(lv.table):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.words = [""]

        # LVGL 9.x: Create styles
        cell_style = lv.style_t()
        cell_style.init()
        cell_style.set_bg_opa(lv.OPA.TRANSP)
        cell_style.set_border_width(0)
        cell_style.set_text_font(lv.font_montserrat_22)

        # Style for number columns (dimmed)
        num_style = lv.style_t()
        num_style.init()
        num_style.set_bg_opa(lv.OPA.TRANSP)
        num_style.set_border_width(0)
        num_style.set_text_font(lv.font_montserrat_22)
        num_style.set_text_opa(lv.OPA._40)

        self.set_column_count(4)
        self.set_row_count(12)
        self.set_column_width(0, 40)
        self.set_column_width(2, 40)
        self.set_column_width(1, 180)
        self.set_column_width(3, 180)

        # LVGL 9.x: Apply styles to table parts
        self.add_style(cell_style, lv.PART.MAIN)
        self.add_style(cell_style, lv.PART.ITEMS)

        for i in range(12):
            self.set_cell_value(i, 0, "%d" % (i + 1))
            self.set_cell_value(i, 2, "%d" % (i + 13))

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
