#!/usr/bin/env python3

"""
Modular Stress Test for Specter DIY Hardware

This is the new modular implementation of the stress test system.
It uses the stresstest package with separate components for each hardware part.

Usage:
- From menu: Import this instead of stresstest.py
"""

from stresstest import StressTest

# For integration with the existing menu system
from gui.screens.screen import Screen

class ModularStressTestScreen(Screen):
    """
    Wrapper class to integrate with existing Specter menu system
    """

    def __init__(self, stress_test_instance=None, show_screen_fn=None):
        print("=== MODULAR STRESS TEST SCREEN INIT ===")
        try:
            print("Calling super().__init__()...")
            super().__init__()

            # Accept the stress_test parameter for compatibility, but create our own
            print("Creating modular stress test...")
            self.old_stress_test = stress_test_instance  # Keep reference to old one if needed
            self.stress_test = StressTest()
            self.initialized = False
            self.show_screen_fn = show_screen_fn  # Function to show sub-screens
            self.test_task = None  # Track the running test task

            # Create GUI immediately (like the original)
            print("Creating GUI elements...")
            self.create_gui()

            print("ModularStressTestScreen init complete")
        except Exception as e:
            print("ModularStressTestScreen init error:", str(e))
            import sys
            sys.print_exception(e)
            raise

    def create_gui(self):
        """Create the GUI elements"""
        from gui.common import add_label, add_button
        from gui.decorators import on_release
        import lvgl as lv

        print("Creating title...")
        # Title
        self.title = add_label("Modular Stress Test", style="title", scr=self)
        self.title.align(self, lv.ALIGN.IN_TOP_MID, 0, 10)

        print("Creating status label...")
        # Status display
        self.status_label = add_label("Ready to initialize", scr=self)
        self.status_label.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

        print("Creating stats label...")
        # Statistics display area (make it scrollable for long text)
        self.stats_label = add_label("Press Initialize to begin", scr=self)
        self.stats_label.align(self.status_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        self.stats_label.set_width(400)  # Set fixed width
        self.stats_label.set_height(150)  # Set fixed height to prevent overlap

        print("Creating initialize button...")
        # Initialize button - use simple Y positioning like the original
        self.init_btn = add_button(
            "Initialize",
            on_release(self.initialize_sync),
            y=350,  # Fixed position
            scr=self
        )

        print("Creating start button...")
        # Start button
        self.start_btn = add_button(
            "Start Test",
            on_release(self.start_test_sync),
            y=430,  # Fixed position
            scr=self
        )

        print("Creating stop button...")
        # Stop button
        self.stop_btn = add_button(
            "Stop Test",
            on_release(self.stop_test_sync),
            y=510,  # Fixed position
            scr=self
        )

        print("Creating config button...")
        # Configuration button
        self.config_btn = add_button(
            lv.SYMBOL.SETTINGS + " Config",
            on_release(self.show_config_sync),
            y=590,  # Fixed position - proper 80px spacing
            scr=self
        )

        print("Creating back button...")
        # Back button
        self.back_btn = add_button(
            lv.SYMBOL.LEFT + " Back",
            on_release(self.go_back),
            y=670,  # Fixed position - proper 80px spacing
            scr=self
        )

        print("GUI creation complete")

    def initialize_sync(self):
        """Synchronous wrapper for initialize"""
        print("Initialize button pressed")
        import asyncio
        asyncio.create_task(self.initialize_async())

    async def initialize_async(self):
        """Initialize the stress test components"""
        try:
            print("=== INITIALIZING MODULAR STRESS TEST ===")
            self.status_label.set_text("Initializing...")

            # Initialize the stress test
            await self.stress_test.initialize()

            # Update status
            self.status_label.set_text("Initialized - Ready to test")

            # Show component status
            self.update_component_status_display()

            # Enable start button
            import lvgl as lv
            try:
                # Try the MicroPython LVGL method
                self.start_btn.clear_state(lv.STATE.DISABLED)
            except:
                try:
                    # Try older LVGL method
                    self.start_btn.clear_state(lv.btn.STATE.INA)
                except:
                    # Fallback - just enable the button
                    print("Could not clear button state, using fallback")

            self.initialized = True
            print("Initialization complete")

        except Exception as e:
            print("Initialization failed:", str(e))
            self.status_label.set_text("Initialization failed")
            self.stats_label.set_text("Error: " + str(e))

    def update_component_status_display(self):
        """Update the display to show component status after initialization"""
        lines = []

        # Sleep duration configuration
        sleep_duration = self.stress_test.get_sleep_duration()
        lines.append("Sleep Duration: " + str(sleep_duration) + "ms")
        lines.append("")

        # Component status - check both enabled state and availability
        components = [
            ("QR Scanner", "qr_scanner", self.stress_test.qr_tester),
            ("Smartcard", "smartcard", self.stress_test.smartcard_tester),
            ("Storage", "storage", self.stress_test.storage_tester),
            ("SD Card", "sdcard", self.stress_test.sdcard_tester)
        ]

        for name, component_key, tester in components:
            # Check if component is enabled first
            if not self.stress_test.get_component_enabled(component_key):
                status = "○ " + name + ": Disabled"
            elif tester.is_available():
                status = "✓ " + name + ": " + tester.get_status()
            else:
                status = "✗ " + name + ": Not available"
            lines.append(status)

        lines.append("")
        lines.append("Press Start Test to begin continuous testing")

        self.stats_label.set_text("\n".join(lines))

    def start_test_sync(self):
        """Synchronous wrapper for start test"""
        print("Start test button pressed")
        if self.initialized:
            import asyncio
            asyncio.create_task(self.start_test_async())
        else:
            print("Not initialized yet")

    async def start_test_async(self):
        """Start the continuous stress test"""
        try:
            # Check if a test is already running
            if self.test_task is not None:
                print("WARNING: Test is already running, stopping it first...")
                await self.stop_test_and_wait()

            print("=== STARTING MODULAR STRESS TEST ===")

            # Read and display current sleep duration before starting
            current_sleep = self.stress_test.get_sleep_duration()
            print("Starting test with sleep duration:", current_sleep, "ms")

            self.status_label.set_text("Running continuous test...")

            # Set up the update callback to update our stats display
            def update_stats_display(stats_text):
                if self.stats_label:
                    self.stats_label.set_text(stats_text)

            # Start the continuous stress test with callback
            self.stress_test.running = True
            self.stress_test.stats_update_callback = update_stats_display

            # Store the task reference
            import asyncio
            self.test_task = asyncio.create_task(self.stress_test.run_continuous_test())

            # Wait for it to complete
            await self.test_task

            # Clear the task reference
            self.test_task = None

            # Update status when stopped (but keep the last stats)
            self.status_label.set_text("Test stopped")
            # Don't clear the stats - keep the last results visible

            print("Continuous stress test stopped")

        except Exception as e:
            print("Stress test failed:", str(e))
            self.status_label.set_text("Test failed")
            self.stats_label.set_text("Error: " + str(e))
            self.test_task = None

    def stop_test_sync(self):
        """Stop the continuous test"""
        print("Stop test button pressed")
        import asyncio
        asyncio.create_task(self.stop_test_and_wait())

    async def stop_test_and_wait(self):
        """Stop the test and wait for it to actually complete"""
        if self.stress_test:
            print("Setting running flag to False...")
            self.stress_test.running = False
            self.status_label.set_text("Stopping test...")

            # Wait for the test task to actually complete
            if self.test_task is not None:
                print("Waiting for test task to complete...")
                try:
                    import asyncio
                    # Wait up to 3 seconds for the test to stop (sleep is now chunked into 100ms pieces)
                    await asyncio.wait_for(self.test_task, timeout=3.0)
                    print("Test task completed successfully")
                    self.status_label.set_text("Test stopped")
                    print("Test fully stopped")
                except asyncio.TimeoutError:
                    print("WARNING: Test task did not stop within timeout")
                    self.status_label.set_text("Test unstoppable")
                except Exception as e:
                    print("Error waiting for test task:", str(e))
                    self.status_label.set_text("Test stopped (error)")
                finally:
                    self.test_task = None
            else:
                self.status_label.set_text("Test stopped")
                print("Test fully stopped")

    def show_config_sync(self):
        """Show configuration screen"""
        print("Config button pressed")
        import asyncio
        asyncio.create_task(self.show_config_async())

    async def show_config_async(self):
        """Show the configuration screen"""
        try:
            from stresstest.config_screen import StressTestConfigScreen
            config_screen = StressTestConfigScreen(self.stress_test)

            if self.show_screen_fn:
                # Use the provided show_screen function
                result = await self.show_screen_fn(config_screen)
                print("Configuration screen closed with result:", result)
                print("Returning to main stress test screen")
                # The main screen should automatically be reactivated by the GUI system
            else:
                print("No show_screen function available")
        except Exception as e:
            print("Error showing config screen:", str(e))
            import sys
            sys.print_exception(e)

    def go_back(self):
        """Go back to main menu"""
        print("Back button pressed")
        import asyncio
        asyncio.create_task(self.go_back_async())

    async def go_back_async(self):
        """Async version of go_back to properly stop test"""
        # Stop any running test first and wait for it
        if self.stress_test and self.stress_test.running:
            print("Stopping test before going back...")
            await self.stop_test_and_wait()
        self.set_value(None)



    async def result(self):
        """Wait for the stress test to complete"""
        print("=== STRESS TEST RESULT ===")
        # Wait for user to interact with the screen (press back button)
        # The back button calls self.set_value(None) which will end this wait
        return await super().result()



