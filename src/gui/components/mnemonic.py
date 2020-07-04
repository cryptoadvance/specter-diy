import lvgl as lv
from .theme import styles

class MnemonicTable(lv.table):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.words = [""]
        # styles
        cell_style = lv.style_t()
        lv.style_copy(cell_style, styles["theme"].style.label.prim)
        cell_style.body.opa = 0
        cell_style.text.font = lv.font_roboto_22

        num_style = lv.style_t()
        lv.style_copy(num_style, cell_style)
        num_style.text.opa = lv.OPA._40

        self.set_col_cnt(4)
        self.set_row_cnt(12)
        self.set_col_width(0, 50)
        self.set_col_width(2, 50)
        self.set_col_width(1, 150)
        self.set_col_width(3, 150)

        self.set_style(lv.page.STYLE.BG, cell_style)
        self.set_style(lv.table.STYLE.CELL1, cell_style)
        self.set_style(lv.table.STYLE.CELL2, num_style)

        for i in range(12):
            self.set_cell_value(i, 0, "%d" % (i+1))
            self.set_cell_value(i, 2, "%d" % (i+13))
            self.set_cell_type(i, 0, lv.table.STYLE.CELL2)
            self.set_cell_type(i, 2, lv.table.STYLE.CELL2)

    def set_mnemonic(self, mnemonic:str):
        self.words = mnemonic.split()
        self.update()

    def update(self):
        for i in range(24):
            row = i%12
            col = 1+2*(i//12)
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
        if len(self.words) == 0:
            self.words.append(word)
        else:
            self.words[-1] = word
        self.words.append("")
        self.update()

    def add_char(self, c):
        if len(self.words) == 0:
            self.words.append(c)
        else:
            self.words[-1] += c
        self.update()
