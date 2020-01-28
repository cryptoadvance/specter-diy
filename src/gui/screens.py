import lvgl as lv
from .common import *
from .decorators import *
from .popups import alert
from pin import Secret, Key, Pin, antiphishing_word, Factory_settings

# queued screens
@queued
def ask_pin(first_time_usage, callback):
    scr = lv.scr_act()
    scr.clean()
    first_time_title = "Choose a PIN code"
    title = "Enter your PIN code"
    if first_time_usage:
        title = first_time_title
    title_lbl = add_label(title, y=PADDING, style="title")
    btnm = lv.btnm(scr)
    btnm.set_map([
        "1","2","3","\n",
        "4","5","6","\n",
        "7","8","9","\n",
        lv.SYMBOL.CLOSE,"0",lv.SYMBOL.OK,""
    ])
    btnm.set_width(HOR_RES)
    btnm.set_height(HOR_RES)
    btnm.align(scr, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

    pin_lbl = lv.ta(scr)
    pin_lbl.set_text("")
    pin_lbl.set_pwd_mode(True)
    style = lv.style_t()
    lv.style_copy(style, styles["theme"].style.ta.oneline)
    style.text.font = lv.font_roboto_28
    style.text.color = lv.color_hex(0xffffff)
    style.text.letter_space = 15
    pin_lbl.set_style(lv.label.STYLE.MAIN, style)
    pin_lbl.set_width(HOR_RES-2*PADDING)
    pin_lbl.set_x(PADDING)
    pin_lbl.set_y(PADDING+50)
    pin_lbl.set_cursor_type(lv.CURSOR.HIDDEN)
    pin_lbl.set_one_line(True)
    pin_lbl.set_text_align(lv.label.ALIGN.CENTER)
    pin_lbl.set_pwd_show_time(0)

    instruct_txt = "Device tamper check.\nThese words should remain #ffffff the same every time#:"
    instruct_label = add_label(instruct_txt, 180, style="hint")
    instruct_label.set_recolor(True)
    antiphish_label = add_label(antiphishing_word(""), 250)
    Pin.read_counter()

    def cb(obj, event):
        nonlocal first_time_usage
        if event == lv.EVENT.RELEASED:
            c = obj.get_active_btn_text()
            if c is None:
                return
            if c == lv.SYMBOL.CLOSE:
                pin_lbl.set_text("")
                antiphish_label.set_text(antiphishing_word(""))
            elif c == lv.SYMBOL.OK:
                # FIXME: check PIN len
                Key.generate_key(pin_lbl.get_text());
                if first_time_usage:
                    Secret.save_secret(alert);
                    callback()
                else:
                    Pin.counter -= 1
                    Pin.save_counter(alert)
                    if Pin.is_pin_valid():
                        Pin.reset_counter(alert)
                        callback()
                    else:
                        instruct_label.set_text("#f07070 Wrong pin: %d/%d #" % (Pin.counter, Pin.ATTEMPTS_MAX))
                        if Pin.counter <= 0:
                            Factory_settings.restore(alert)
                            Secret.generate_secret()
                            alert("Security","Device has been factory reset!")
                            first_time_usage = True
                            title_lbl.set_text(first_time_title)
                            instruct_label.set_text(instruct_txt)
                pin_lbl.set_text("")
                antiphish_label.set_text(antiphishing_word(""))
            else:
                instruct_label.set_text(instruct_txt)
                pin_lbl.add_text(c)
                word = antiphishing_word(pin_lbl.get_text())
                antiphish_label.set_text(antiphish_label.get_text() + " " + word)

    btnm.set_event_cb(cb);

@queued
def create_menu(buttons=[], title="What do you want to do?", y0=100, cb_back=None):
    scr = lv.scr_act()
    scr.clean()
    add_label(title, style="title")
    y = y0
    for text, callback in buttons:
        add_button(text, on_release(callback), y=y)
        y+=100
    if cb_back is not None:
        add_button(lv.SYMBOL.LEFT+" Back", on_release(cb_back))

@queued
def show_progress(title, text, callback=None):
    scr = lv.scr_act()
    scr.clean()
    add_label(title, style="title")
    add_label(text, y=200)
    if callback is not None:
        add_button("Cancel", on_release(callback))

@queued
def new_mnemonic(mnemonic, 
                 cb_continue, cb_back, cb_update=None, 
                 title="Your new recovery phrase:"):
    """Makes the new mnemonic screen with a slider to change number of words"""
    scr = lv.scr_act()
    scr.clean()
    add_label(title, style="title")
    table = add_mnemonic_table(mnemonic, y=100)

    if cb_update is not None:
        wordcount = len(mnemonic.split())
        slider = lv.slider(scr)
        slider.set_width(HOR_RES-2*PADDING)
        slider.set_range(0, 4)
        slider.set_pos(PADDING, 600)
        slider.set_value((wordcount-12)//3, lv.ANIM.OFF)
        lbl = add_label("Number of words: %d" % wordcount, y=550)
        def cb_upd(obj, event):
            if event == lv.EVENT.VALUE_CHANGED:
                wordcount = slider.get_value()*3+12
                lbl.set_text("Number of words: %d" % wordcount)
                mnemonic = cb_update(wordcount)
                table_set_mnemonic(table, mnemonic)
        slider.set_event_cb(cb_upd)
    def cb_prev(obj, event):
        if event == lv.EVENT.RELEASED:
            cb_back()
    def cb_next(obj, event):
        if event == lv.EVENT.RELEASED:
            cb_continue()
    add_button_pair("Back", cb_prev, "Continue", cb_next)

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

@queued
def ask_for_password(cb_continue, title="Enter your password (optional)"):
    scr = lv.scr_act()
    scr.clean()
    add_label(title, style="title")

    btnm = lv.btnm(scr)
    btnm.set_map(CHARSET)
    btnm.set_width(HOR_RES)
    btnm.set_height(VER_RES//3)
    btnm.align(scr, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

    ta = lv.ta(scr)
    ta.set_text("")
    # ta.set_pwd_mode(True)
    ta.set_width(HOR_RES-2*PADDING)
    ta.set_x(PADDING)
    ta.set_text_align(lv.label.ALIGN.CENTER)
    ta.set_y(PADDING+150)
    ta.set_cursor_type(lv.CURSOR.HIDDEN)
    ta.set_one_line(True)
    # ta.set_pwd_show_time(0)
    def cb(obj, event):
        if event == lv.EVENT.RELEASED:
            c = obj.get_active_btn_text()
            if c[0] == lv.SYMBOL.LEFT:
                ta.del_char()
            elif c == lv.SYMBOL.UP or c == lv.SYMBOL.DOWN:
                for i,ch in enumerate(CHARSET):
                    if ch.isalpha():
                        if c == lv.SYMBOL.UP:
                            CHARSET[i] = CHARSET[i].upper()
                        else:
                            CHARSET[i] = CHARSET[i].lower()
                    elif ch == lv.SYMBOL.UP:
                        CHARSET[i] = lv.SYMBOL.DOWN
                    elif ch == lv.SYMBOL.DOWN:
                        CHARSET[i] = lv.SYMBOL.UP
                btnm.set_map(CHARSET)
            elif c == "#@":
                btnm.set_map(CHARSET_EXTRA)
            elif c == "aA":
                btnm.set_map(CHARSET)
            elif c[0] == lv.SYMBOL.CLOSE:
                ta.set_text("")
            elif c[0] == lv.SYMBOL.OK:
                cb_continue(ta.get_text())
                ta.set_text("")
            else:
                ta.add_text(c)
    btnm.set_event_cb(cb)

# global
words = []

@queued
def ask_for_mnemonic(cb_continue, cb_back, 
                     check_mnemonic=None, words_lookup=None,
                     title="Enter your recovery phrase"):
    scr = lv.scr_act()
    scr.clean()
    add_label(title, style="title")
    table = add_mnemonic_table("", y=70)

    btnm = lv.btnm(scr)
    btnm.set_map([
        "Q","W","E","R","T","Y","U","I","O","P","\n",
        "A","S","D","F","G","H","J","K","L","\n",
        "Z","X","C","V","B","N","M",lv.SYMBOL.LEFT,"\n",
        lv.SYMBOL.LEFT+" Back","Next word",lv.SYMBOL.OK+" Done",""
    ])

    if words_lookup is not None:
        # Next word button inactive
        btnm.set_btn_ctrl(28, lv.btnm.CTRL.INACTIVE)
    if check_mnemonic is not None:
        # Done inactive
        btnm.set_btn_ctrl(29, lv.btnm.CTRL.INACTIVE)
    btnm.set_width(HOR_RES)
    btnm.set_height(VER_RES//3)
    btnm.align(scr, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

    def cb(obj, event):
        global words
        if event == lv.EVENT.RELEASED:
            c = obj.get_active_btn_text()
            num = obj.get_active_btn()
            # if inactive button is clicked - return
            if obj.get_btn_ctrl(num,lv.btnm.CTRL.INACTIVE):
                return
            if c == lv.SYMBOL.LEFT+" Back":
                cb_back()
            elif c == lv.SYMBOL.LEFT:
                if len(words[-1]) > 0:
                    words[-1] = words[-1][:-1]
                elif len(words) > 0:
                    words = words[:-1]
                table_set_mnemonic(table, " ".join(words))
            elif c == "Next word":
                if words_lookup is not None and len(words[-1])>=2:
                    candidates = words_lookup(words[-1])
                    if len(candidates) == 1:
                        words[-1] = candidates[0]
                words.append("")
                table_set_mnemonic(table, " ".join(words))
            elif c == lv.SYMBOL.OK+" Done":
                pass
            else:
                if len(words) == 0:
                    words.append("")
                words[-1] = words[-1]+c.lower()
                table_set_mnemonic(table, " ".join(words))

            mnemonic = None
            if words_lookup is not None:
                btnm.set_btn_ctrl(28, lv.btnm.CTRL.INACTIVE)
                if len(words) > 0 and len(words[-1])>=2:
                    candidates = words_lookup(words[-1])
                    if len(candidates) == 1 or words[-1] in candidates:
                        btnm.clear_btn_ctrl(28, lv.btnm.CTRL.INACTIVE)
                        mnemonic = " ".join(words[:-1])
                        if len(candidates) == 1:
                            mnemonic += " "+candidates[0]
                        else:
                            mnemonic += " "+words[-1]
            else:
                mnemonic = " ".join(words)
            if check_mnemonic is not None and mnemonic is not None:
                if check_mnemonic(mnemonic):
                    btnm.clear_btn_ctrl(29, lv.btnm.CTRL.INACTIVE)
                else:
                    btnm.set_btn_ctrl(29, lv.btnm.CTRL.INACTIVE)
            # if user was able to click this button then mnemonic is correct
            if c == lv.SYMBOL.OK+" Done":
                cb_continue(mnemonic)

    btnm.set_event_cb(cb);
