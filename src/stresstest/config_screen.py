# Stress Test Configuration Screen

import lvgl as lv
import asyncio
from gui.screens.screen import Screen
from gui.common import add_label, add_button
from gui.decorators import on_release
from .sleep_config_screen import StressTestSleepConfigScreen


class StressTestConfigScreen(Screen):
    """Main configuration screen for stress test parameters"""

    def __init__(self, stress_test):
        super().__init__()
        self.stress_test = stress_test
        self.closing = False  # Flag to prevent multiple back button presses

        # Title
        self.title = add_label("Stress Test Config", style="title", scr=self)

        # Component enable/disable switches
        y = 60
        self.components_label = add_label("Test Components:", y=y, scr=self)
        y += 40

        # Store switches for later retrieval
        self.component_switches = {}

        # Define components with their display names and keys
        components = [
            ("QR Scanner", "qr_scanner"),
            ("Smartcard", "smartcard"),
            ("Storage", "storage"),
            ("SD Card", "sdcard")
        ]

        for display_name, component_key in components:
            # Component label
            label = add_label(display_name, y=y, scr=self)

            # Create switch
            switch = lv.sw(self)
            switch.align(label, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

            # Add ON/OFF label overlay
            switch_label = add_label(" OFF                              ON  ", scr=self)
            switch_label.align(switch, lv.ALIGN.CENTER, 0, 0)

            # Set initial state based on current configuration
            if self.stress_test.get_component_enabled(component_key):
                switch.on(lv.ANIM.OFF)

            # Store switch reference
            self.component_switches[component_key] = switch

            y += 80

        # Add separator
        y += 20
        self.separator_label = add_label("─" * 30, y=y, scr=self, style="hint")
        y += 40

        # Sleep duration button - opens subpage
        current_duration = self.stress_test.get_sleep_duration()
        self.sleep_btn = add_button(
            "Sleep Duration: " + str(current_duration) + "ms " + lv.SYMBOL.RIGHT,
            on_release(self.open_sleep_config_sync),
            y=y,
            scr=self
        )
        y += 80

        # Back button
        self.back_btn = add_button(
            lv.SYMBOL.LEFT + " Back",
            on_release(self.go_back),
            y=y,
            scr=self
        )

    def open_sleep_config_sync(self):
        """Synchronous wrapper to open sleep duration config subpage"""
        print("Sleep duration button clicked - opening subpage")
        asyncio.create_task(self.open_sleep_config())

    async def open_sleep_config(self):
        """Open the sleep duration configuration subpage"""
        # Save the current screen
        old_screen = lv.scr_act()

        # Create and load the sleep config screen
        sleep_config_screen = StressTestSleepConfigScreen(self.stress_test)
        lv.scr_load(sleep_config_screen)

        # Wait for the screen to complete
        await sleep_config_screen.result()

        # Restore the config screen
        lv.scr_load(old_screen)

        # Delete the sleep config screen
        sleep_config_screen.del_async()

        # Update the button text when returning from subpage
        current_duration = self.stress_test.get_sleep_duration()
        self.sleep_btn.get_child(None).set_text("Sleep Duration: " + str(current_duration) + "ms " + lv.SYMBOL.RIGHT)

    def go_back(self):
        """Return to the previous screen and save component states"""
        if self.closing:
            return  # Already closing, ignore additional presses
        self.closing = True

        # Save component enable/disable states
        for component_key, switch in self.component_switches.items():
            enabled = switch.get_state()
            self.stress_test.set_component_enabled(component_key, enabled)
            print("Saved component state:", component_key, "=", enabled)

        print("Config screen back button pressed - closing")
        self.set_value(None)

