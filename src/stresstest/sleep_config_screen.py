# Stress Test Sleep Duration Configuration Screen

import lvgl as lv
from gui.screens.screen import Screen
from gui.common import add_label, add_button
from gui.decorators import on_release


class StressTestSleepConfigScreen(Screen):
    """Subpage for configuring sleep duration between test iterations"""

    def __init__(self, stress_test):
        super().__init__()
        self.stress_test = stress_test
        self.closing = False

        # Title
        self.title = add_label("Sleep Duration Config", style="title", scr=self)

        y = 80

        # Sleep duration configuration
        self.duration_label = add_label("Sleep Duration (ms):", y=y, scr=self)
        y += 40

        # Current value display
        current_duration = self.stress_test.get_sleep_duration()
        self.value_label = add_label(str(current_duration), y=y, scr=self, style="title")
        y += 60

        # Reset button
        self.reset_btn = add_button(
            "Reset to 0ms",
            on_release(self.reset_duration),
            y=y,
            scr=self
        )
        y += 80

        # Adjustment buttons
        self.decrease_100_btn = add_button(
            "-100ms",
            on_release(self.decrease_100),
            y=y,
            scr=self
        )
        y += 80

        self.increase_100_btn = add_button(
            "+100ms",
            on_release(self.increase_100),
            y=y,
            scr=self
        )
        y += 80

        self.decrease_500_btn = add_button(
            "-500ms",
            on_release(self.decrease_500),
            y=y,
            scr=self
        )
        y += 80

        self.increase_500_btn = add_button(
            "+500ms",
            on_release(self.increase_500),
            y=y,
            scr=self
        )
        y += 80

        # Info label
        self.info_label = add_label(
            "Range: 0ms - 10000ms\nAdditional delay between tests",
            y=y,
            scr=self,
            style="hint"
        )
        y += 80

        # Back button
        self.back_btn = add_button(
            lv.SYMBOL.LEFT + " Back",
            on_release(self.go_back),
            y=y,
            scr=self
        )

    def reset_duration(self):
        """Reset sleep duration to 0ms (default)"""
        self.stress_test.set_sleep_duration(0)
        self.update_display()

    def increase_100(self):
        """Increase sleep duration by 100ms"""
        current = self.stress_test.get_sleep_duration()
        new_duration = min(current + 100, 10000)
        self.stress_test.set_sleep_duration(new_duration)
        self.update_display()

    def decrease_100(self):
        """Decrease sleep duration by 100ms"""
        current = self.stress_test.get_sleep_duration()
        new_duration = max(current - 100, 100)
        self.stress_test.set_sleep_duration(new_duration)
        self.update_display()

    def increase_500(self):
        """Increase sleep duration by 500ms"""
        current = self.stress_test.get_sleep_duration()
        new_duration = min(current + 500, 10000)
        self.stress_test.set_sleep_duration(new_duration)
        self.update_display()

    def decrease_500(self):
        """Decrease sleep duration by 500ms"""
        current = self.stress_test.get_sleep_duration()
        new_duration = max(current - 500, 100)
        self.stress_test.set_sleep_duration(new_duration)
        self.update_display()

    def update_display(self):
        """Update the current value display"""
        current_duration = self.stress_test.get_sleep_duration()
        self.value_label.set_text(str(current_duration))

    def go_back(self):
        """Return to the previous screen"""
        if self.closing:
            return
        self.closing = True
        print("Sleep config screen back button pressed - closing")
        self.set_value(None)

