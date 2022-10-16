import lvgl as lv
from .prompt import Prompt
from ..common import add_label, add_button
from ..decorators import on_release

class HostSettings(Prompt):
    def __init__(self, controls, title="Host setttings", note=None, controls_empty_text="No settings available"):
        super().__init__(title, "")
        y = 40
        if note is not None:
            self.note = add_label(note, style="hint", scr=self)
            self.note.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
            y += self.note.get_height()
        self.controls = controls
        self.switches = []
        for control in controls:
            label = add_label(control["label"], y, scr=self.page)
            hint = add_label(
                control.get("hint", ""),
                y + 30,
                scr=self.page,
                style="hint",
            )
            switch = lv.sw(self.page)
            switch.align(hint, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
            lbl = add_label(" OFF                              ON  ", scr=self.page)
            lbl.align(switch, lv.ALIGN.CENTER, 0, 0)
            if control.get("value", False):
                switch.on(lv.ANIM.OFF)
            self.switches.append(switch)
            y = lbl.get_y() + 80
        else:
            label = add_label(controls_empty_text, y, scr=self.page)
        self.confirm_button.set_event_cb(on_release(self.update))
        self.cancel_button.set_event_cb(on_release(lambda: self.set_value(None)))

    def update(self):
        self.set_value([switch.get_state() for switch in self.switches])

class DevSettings(Prompt):
    def __init__(self, dev=False, usb=False, note=None):
        super().__init__("Device settings", "")
        if note is not None:
            self.note = add_label(note, style="hint", scr=self)
            self.note.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
        y = 70
        usb_label = add_label("USB communication", y, scr=self.page)
        usb_hint = add_label(
            "If USB is enabled the device will be able "
            "to talk to your computer. This increases "
            "attack surface but sometimes makes it "
            "more convenient to use.",
            y + 40,
            scr=self.page,
            style="hint",
        )
        self.usb_switch = lv.sw(self.page)
        self.usb_switch.align(usb_hint, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
        lbl = add_label(" OFF                              ON  ", scr=self.page)
        lbl.align(self.usb_switch, lv.ALIGN.CENTER, 0, 0)
        if usb:
            self.usb_switch.on(lv.ANIM.OFF)

        # y += 200
        # dev_label = add_label("Developer mode", y, scr=self.page)
        # dev_hint = add_label(
        #     "In developer mode internal flash will "
        #     "be mounted to your computer so you could "
        #     "edit files, but your secrets will be visible as well. "
        #     "Also enables interactive shell through miniUSB port.",
        #     y + 40,
        #     scr=self.page,
        #     style="hint",
        # )
        # self.dev_switch = lv.sw(self.page)
        # self.dev_switch.align(dev_hint, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
        # lbl = add_label(" OFF                              ON  ", scr=self.page)
        # lbl.align(self.dev_switch, lv.ALIGN.CENTER, 0, 0)
        # if dev:
        #     self.dev_switch.on(lv.ANIM.OFF)
        self.confirm_button.set_event_cb(on_release(self.update))
        self.cancel_button.set_event_cb(on_release(lambda: self.set_value(None)))

        self.wipebtn = add_button(
            lv.SYMBOL.TRASH + " Wipe device", on_release(self.wipe), scr=self
        )
        self.wipebtn.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, -140)
        style = lv.style_t()
        lv.style_copy(style, self.wipebtn.get_style(lv.btn.STYLE.REL))
        style.body.main_color = lv.color_hex(0x951E2D)
        style.body.grad_color = lv.color_hex(0x951E2D)
        self.wipebtn.set_style(lv.btn.STYLE.REL, style)

    def wipe(self):
        self.set_value(
            {
                "dev": False, # self.dev_switch.get_state(),
                "usb": self.usb_switch.get_state(),
                "wipe": True,
            }
        )

    def update(self):
        self.set_value(
            {
                "dev": False, # self.dev_switch.get_state(),
                "usb": self.usb_switch.get_state(),
                "wipe": False,
            }
        )
