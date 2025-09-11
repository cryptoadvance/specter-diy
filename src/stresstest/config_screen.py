# Stress Test Configuration Screen

import lvgl as lv
from gui.screens.screen import Screen
from gui.common import add_label, add_button
from gui.decorators import on_release


class StressTestConfigScreen(Screen):
    """Configuration screen for stress test parameters"""
    
    def __init__(self, stress_test):
        super().__init__()
        self.stress_test = stress_test
        self.closing = False  # Flag to prevent multiple back button presses
        
        # Title
        self.title = add_label("Stress Test Config", style="title", scr=self)
        
        # Sleep duration configuration
        self.duration_label = add_label("Sleep Duration (ms):", y=80, scr=self)
        
        # Current value display
        current_duration = self.stress_test.get_sleep_duration()
        self.value_label = add_label(str(current_duration), y=120, scr=self, style="title")
        
        # Reset button
        self.reset_btn = add_button(
            "Reset to 500ms",
            on_release(self.reset_duration),
            y=160,
            scr=self
        )

        # Adjustment buttons
        self.decrease_100_btn = add_button(
            "-100ms",
            on_release(self.decrease_100),
            y=200,
            scr=self
        )

        self.increase_100_btn = add_button(
            "+100ms",
            on_release(self.increase_100),
            y=250,
            scr=self
        )

        self.decrease_500_btn = add_button(
            "-500ms",
            on_release(self.decrease_500),
            y=300,
            scr=self
        )

        self.increase_500_btn = add_button(
            "+500ms",
            on_release(self.increase_500),
            y=350,
            scr=self
        )
        
        # Info label
        self.info_label = add_label(
            "Range: 100ms - 10000ms\nLower = faster testing",
            y=410,
            scr=self,
            style="hint"
        )

        # Back button
        self.back_btn = add_button(
            lv.SYMBOL.LEFT + " Back",
            on_release(self.go_back),
            y=480,
            scr=self
        )
        
    def reset_duration(self):
        """Reset sleep duration to 500ms"""
        self.stress_test.set_sleep_duration(500)
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
            return  # Already closing, ignore additional presses
        self.closing = True
        print("Config screen back button pressed - closing")
        self.set_value(None)
