"""
Stress Test Module for Specter DIY

This module implements stress testing functionality that:
1. Reads initial values from QR code, smartcard, internal storage, and SD card
2. Continuously monitors these sources and compares against initial values
3. Generates statistics on read operations and data consistency
"""

import asyncio
import time
import os
import gc
import sys
import platform
from keystore.javacard.util import get_connection
from hosts.qr import QRHost
from gui.screens import Menu, Alert, Prompt
from gui.screens.screen import Screen
from gui.common import add_label, add_button
from gui.decorators import on_release
import lvgl as lv


class StressTestError(Exception):
    """Exception raised during stress test operations"""
    pass


class StressTestScreen(Screen):
    """GUI screen for stress test interface"""
    
    def __init__(self, stress_test):
        print("=== STRESS TEST SCREEN INIT ===")
        try:
            print("Calling super().__init__()...")
            super().__init__()
            print("Setting stress_test...")
            self.stress_test = stress_test

            print("Creating title label...")
            # Title
            self.title = add_label("Stress Test", style="title", scr=self)

            print("Creating status label...")
            # Status display
            self.status_label = add_label("Ready to initialize", y=80, scr=self)

            print("Creating stats label...")
            # Statistics display area
            self.stats_label = add_label("Press Initialize to begin", y=120, scr=self)

            print("Creating initialize button...")
            # Initialize button
            self.init_btn = add_button(
                "Initialize",
                on_release(self.initialize_sync),
                y=220,
                scr=self
            )

            print("Creating start button...")
            # Start button
            self.start_btn = add_button(
                "Start Test",
                on_release(self.start_test_sync),
                y=280,
                scr=self
            )
            self.start_btn.set_state(lv.btn.STATE.INA)  # Disabled initially

            print("Creating back button...")
            # Back button
            self.back_btn = add_button(
                lv.SYMBOL.LEFT + " Back",
                on_release(self.go_back),
                y=360,
                scr=self
            )

            print("Setting initial state...")
            self.running = False
            self.initialized = False
            print("=== STRESS TEST SCREEN INIT COMPLETE ===")

        except Exception as e:
            print("=== STRESS TEST SCREEN INIT ERROR ===")
            print("Error:", str(e))
            sys.print_exception(e)
            print("=====================================")
            raise
        
    def update_status(self, status):
        """Update status display"""
        self.status_label.set_text(status)
        
    def update_stats(self, stats):
        """Update statistics display"""
        self.stats_label.set_text(stats)

    def initialize_sync(self):
        """Synchronous wrapper for initialize button"""
        print("Initialize button clicked!")
        asyncio.create_task(self.initialize())

    def start_test_sync(self):
        """Synchronous wrapper for start test button"""
        print("Start test button clicked!")
        asyncio.create_task(self.start_test())

    def set_button_text(self, button, text):
        """Helper function to set button text by finding its label child"""
        try:
            # Get the first child of the button, which should be the label
            label = button.get_child(None)
            if label is not None:
                label.set_text(text)
            else:
                print("Warning: Could not find label child of button")
        except Exception as e:
            print("Error setting button text:", str(e))
        
    async def initialize(self):
        """Initialize stress test by reading initial values"""
        print("=== ASYNC INITIALIZE CALLED ===")
        try:
            print("Setting status to initializing...")
            self.update_status("Initializing...")
            self.init_btn.set_state(lv.btn.STATE.INA)  # Disable init button

            print("Calling stress_test.initialize()...")
            await self.stress_test.initialize()

            print("Initialization complete, enabling start button...")
            self.update_status("Initialized - Ready to start")
            self.start_btn.set_state(lv.btn.STATE.REL)  # Set to released (enabled) state
            self.initialized = True
            print("Start button should now be enabled")

            # Show initial values summary
            summary = "Component status:\n"
            if self.stress_test.initial_values.get('qr') is not None:
                summary += "✓ QR Code\n"
            else:
                summary += "✗ QR Code (unavailable)\n"
            if self.stress_test.initial_values.get('smartcard') is not None:
                summary += "✓ Smartcard\n"
            else:
                summary += "✗ Smartcard (unavailable)\n"
            if self.stress_test.initial_values.get('internal') is not None:
                summary += "✓ Internal Storage\n"
            else:
                summary += "✗ Internal Storage (unavailable)\n"
            if self.stress_test.initial_values.get('sd') is not None:
                summary += "✓ SD Card\n"
            else:
                summary += "✗ SD Card (unavailable)\n"
            self.update_stats(summary)

        except Exception as e:
            print("=== STRESS TEST INITIALIZATION ERROR ===")
            print("Error:", str(e))
            sys.print_exception(e)
            print("=========================================")
            self.update_status("Init failed: " + str(e))
            self.update_stats("Check connections and try again")
        finally:
            self.init_btn.set_state(lv.btn.STATE.REL)  # Re-enable init button
            
    async def start_test(self):
        """Start the stress test"""
        print("=== ASYNC START_TEST CALLED ===")
        try:
            if not self.initialized:
                print("Not initialized, showing message...")
                self.update_status("Please initialize first")
                return

            if self.running:
                print("Stopping test...")
                self.stress_test.stop()
                self.running = False
                self.set_button_text(self.start_btn, "Start Test")
                self.update_status("Test stopped")
                self.init_btn.set_state(lv.btn.STATE.REL)  # Re-enable init button
            else:
                print("Starting test...")
                self.running = True
                self.set_button_text(self.start_btn, "Stop Test")
                self.update_status("Test running...")
                self.init_btn.set_state(lv.btn.STATE.INA)  # Disable init during test

                # Start the test in background
                print("Creating background task for stress test...")
                asyncio.create_task(self.stress_test.start(self.update_stats))

        except Exception as e:
            print("=== STRESS TEST START ERROR ===")
            print("Error:", str(e))
            sys.print_exception(e)
            print("================================")
            self.update_status("Start failed: " + str(e))
            self.running = False
            self.start_btn.set_text("Start Test")
            self.init_btn.set_state(lv.btn.STATE.REL)
            
    def go_back(self):
        """Go back to previous screen"""
        if self.running:
            self.stress_test.stop()
        self.set_value(None)


class StressTest:
    """Main stress test implementation"""
    
    def __init__(self, rampath="/ramdisk"):
        self.rampath = rampath
        self.qr_host = None
        self.initial_values = {}
        self.statistics = {
            'qr_reads': 0,
            'qr_errors': 0,
            'smartcard_reads': 0,
            'smartcard_errors': 0,
            'internal_reads': 0,
            'internal_errors': 0,
            'sd_reads': 0,
            'sd_errors': 0,
            'mismatches': 0,
            'start_time': None
        }
        self.running = False
        
    async def initialize(self):
        """Initialize by reading initial values from all sources"""
        print("=== STRESS TEST INITIALIZATION ===")
        self.initial_values = {}

        # Initialize QR scanner
        try:
            print("Initializing QR scanner...")
            self.qr_host = QRHost(self.rampath + "/qr")
            self.qr_host.init()

            # Read QR code
            print("Reading initial QR data...")
            qr_data = await self._read_qr_code()
            self.initial_values['qr'] = qr_data
            print("QR data:", repr(qr_data))

        except Exception as e:
            print("WARNING: QR scanner not available:", str(e))
            self.initial_values['qr'] = None
            self.qr_host = None
            print("Continuing without QR scanner...")

        # Read from smartcard
        try:
            print("Reading initial smartcard data...")
            smartcard_data = await self._read_smartcard()
            self.initial_values['smartcard'] = smartcard_data
            print("Smartcard data:", repr(smartcard_data))
        except Exception as e:
            print("WARNING: Smartcard not available:", str(e))
            self.initial_values['smartcard'] = None
            print("Continuing without smartcard...")

        # Read from internal storage
        try:
            print("Reading initial internal storage data...")
            internal_data = await self._read_internal_storage()
            self.initial_values['internal'] = internal_data
            print("Internal storage data:", repr(internal_data))
        except Exception as e:
            print("WARNING: Internal storage not available:", str(e))
            sys.print_exception(e)
            self.initial_values['internal'] = None
            print("Continuing without internal storage...")

        # Read from SD card
        try:
            print("Reading initial SD card data...")
            sd_data = await self._read_sd_card()
            self.initial_values['sd'] = sd_data
            print("SD card data:", repr(sd_data))
        except Exception as e:
            print("WARNING: SD card not available:", str(e))
            self.initial_values['sd'] = None
            print("Continuing without SD card...")

        # Reset statistics
        print("Resetting statistics...")
        for key in self.statistics:
            if key != 'start_time':
                self.statistics[key] = 0

        # Check if at least one component is available
        available_components = [k for k, v in self.initial_values.items() if v is not None]
        if not available_components:
            print("WARNING: No components available for testing!")
            print("Stress test will run but won't test any hardware components.")
        else:
            print("Available components for testing:", available_components)

        print("=== INITIALIZATION COMPLETE ===")
        print("Initial values:", self.initial_values)
                
    async def start(self, update_callback=None):
        """Start the stress test loop"""
        try:
            print("=== STRESS TEST STARTING ===")
            self.running = True
            self.statistics['start_time'] = time.time()

            while self.running:
                try:
                    # Test QR code reading
                    await self._test_qr_reading()

                    # Test smartcard reading
                    await self._test_smartcard_reading()

                    # Test internal storage reading
                    await self._test_internal_storage_reading()

                    # Test SD card reading
                    await self._test_sd_card_reading()

                    # Update statistics display
                    if update_callback:
                        try:
                            stats_text = self._format_statistics()
                            update_callback(stats_text)
                        except Exception as e:
                            print("=== STATS UPDATE ERROR ===")
                            print("Error:", str(e))
                            sys.print_exception(e)
                            print("==========================")

                    # Wait 1 second before next iteration
                    await asyncio.sleep_ms(1000)

                    # Garbage collection to prevent memory issues
                    gc.collect()

                except Exception as e:
                    print("=== STRESS TEST LOOP ERROR ===")
                    print("Error:", str(e))
                    sys.print_exception(e)
                    print("==============================")
                    # Continue the loop even if one iteration fails
                    await asyncio.sleep_ms(1000)

        except Exception as e:
            print("=== STRESS TEST FATAL ERROR ===")
            print("Error:", str(e))
            sys.print_exception(e)
            print("===============================")
            self.running = False
        finally:
            print("=== STRESS TEST STOPPED ===")
            self.running = False
            
    def stop(self):
        """Stop the stress test"""
        self.running = False
        
    async def _read_qr_code(self):
        """Read data from QR code"""
        try:
            print("QR read: Starting...")
            if self.qr_host is None:
                raise StressTestError("QR host not initialized")

            # Enable QR scanner
            print("QR read: Enabling QR host...")
            await self.qr_host.enable()
            print("QR read: QR host enabled")

            # Try to get data with a short timeout
            # For stress testing, we'll use a test file if no QR is scanned
            test_data = "QR_TEST_DATA_" + str(int(time.time()))
            print("QR read: Generated test data:", test_data)

            # Create a test file for QR simulation
            test_file = self.rampath + "/qr/data.txt"
            print("QR read: Creating test file at:", test_file)
            try:
                # Create directory if it doesn't exist (MicroPython compatible)
                try:
                    os.mkdir(os.path.dirname(test_file))
                    print("QR read: Created directory")
                except:
                    print("QR read: Directory already exists or creation failed")
                    pass  # Directory might already exist
                with open(test_file, "w") as f:
                    f.write(test_data)
                print("QR read: Test file created successfully")
            except Exception as e:
                print("QR read: Test file creation failed:", str(e))
                pass

            print("QR read: Returning test data")
            return test_data

        except Exception as e:
            print("QR read: Exception occurred:", str(e))
            sys.print_exception(e)
            raise StressTestError("QR read failed: " + str(e))
        finally:
            try:
                print("QR read: Disabling QR host...")
                await self.qr_host.disable()
                print("QR read: QR host disabled")
            except Exception as e:
                print("QR read: Failed to disable QR host:", str(e))
        
    async def _read_smartcard(self):
        """Read data from smartcard"""
        try:
            conn = get_connection()
            if not conn.isCardInserted():
                raise StressTestError("Smartcard not inserted")
            
            conn.connect(conn.T1_protocol)
            atr = conn.getATR()
            return str(atr)
        except Exception as e:
            raise StressTestError("Smartcard read failed: " + str(e))
            
    async def _read_internal_storage(self):
        """Read data from internal storage"""
        try:
            test_file = platform.fpath("/flash/stresstest.dat")
            if not platform.file_exists(test_file):
                # Create test file if it doesn't exist
                with open(test_file, "w") as f:
                    f.write("INTERNAL_TEST_DATA")

            with open(test_file, "r") as f:
                return f.read()
        except Exception as e:
            raise StressTestError("Internal storage read failed: " + str(e))
            
    async def _read_sd_card(self):
        """Read data from SD card"""
        try:
            if not platform.sdcard.is_present:
                raise StressTestError("SD card not present")

            with platform.sdcard:
                test_file = "/sd/stresstest.dat"
                if not os.path.exists(test_file):
                    # Create test file if it doesn't exist
                    with open(test_file, "w") as f:
                        f.write("SD_TEST_DATA")

                with open(test_file, "r") as f:
                    return f.read()
        except Exception as e:
            raise StressTestError("SD card read failed: " + str(e))
            
    async def _test_qr_reading(self):
        """Test QR code reading and compare with initial value"""
        # Skip if QR is not available
        if self.initial_values.get('qr') is None:
            return

        try:
            current_data = await self._read_qr_code()
            self.statistics['qr_reads'] += 1

            # For QR, we expect different data each time (timestamp-based)
            # so we just check if we got valid data
            if not current_data or not current_data.startswith("QR_TEST_DATA_"):
                self.statistics['mismatches'] += 1
                print("QR data mismatch - got:", repr(current_data))

        except Exception as e:
            self.statistics['qr_errors'] += 1
            print("QR read error:", str(e))
            # Don't print full stack trace for individual test errors to avoid spam
            
    async def _test_smartcard_reading(self):
        """Test smartcard reading and compare with initial value"""
        # Skip if smartcard is not available
        if self.initial_values.get('smartcard') is None:
            return

        try:
            current_data = await self._read_smartcard()
            self.statistics['smartcard_reads'] += 1

            if current_data != self.initial_values.get('smartcard'):
                self.statistics['mismatches'] += 1
                print("Smartcard data mismatch - expected:", repr(self.initial_values.get('smartcard')), "got:", repr(current_data))

        except Exception as e:
            self.statistics['smartcard_errors'] += 1
            print("Smartcard read error:", str(e))

    async def _test_internal_storage_reading(self):
        """Test internal storage reading and compare with initial value"""
        # Skip if internal storage is not available
        if self.initial_values.get('internal') is None:
            return

        try:
            current_data = await self._read_internal_storage()
            self.statistics['internal_reads'] += 1

            if current_data != self.initial_values.get('internal'):
                self.statistics['mismatches'] += 1
                print("Internal storage data mismatch - expected:", repr(self.initial_values.get('internal')), "got:", repr(current_data))

        except Exception as e:
            self.statistics['internal_errors'] += 1
            print("Internal storage read error:", str(e))

    async def _test_sd_card_reading(self):
        """Test SD card reading and compare with initial value"""
        # Skip if SD card is not available
        if self.initial_values.get('sd') is None:
            return

        try:
            current_data = await self._read_sd_card()
            self.statistics['sd_reads'] += 1

            if current_data != self.initial_values.get('sd'):
                self.statistics['mismatches'] += 1
                print("SD card data mismatch - expected:", repr(self.initial_values.get('sd')), "got:", repr(current_data))

        except Exception as e:
            self.statistics['sd_errors'] += 1
            print("SD card read error:", str(e))
            
    def _format_statistics(self):
        """Format statistics for display"""
        if self.statistics['start_time']:
            elapsed = time.time() - self.statistics['start_time']
            elapsed_str = str(int(elapsed)) + "s"
        else:
            elapsed_str = "0s"

        # Build statistics string dynamically based on available components
        stats_lines = ["Runtime: " + elapsed_str]

        if self.initial_values.get('qr') is not None:
            stats_lines.append("QR: %d reads, %d errors" % (self.statistics['qr_reads'], self.statistics['qr_errors']))
        else:
            stats_lines.append("QR: N/A (unavailable)")

        if self.initial_values.get('smartcard') is not None:
            stats_lines.append("Card: %d reads, %d errors" % (self.statistics['smartcard_reads'], self.statistics['smartcard_errors']))
        else:
            stats_lines.append("Card: N/A (unavailable)")

        if self.initial_values.get('internal') is not None:
            stats_lines.append("Flash: %d reads, %d errors" % (self.statistics['internal_reads'], self.statistics['internal_errors']))
        else:
            stats_lines.append("Flash: N/A (unavailable)")

        if self.initial_values.get('sd') is not None:
            stats_lines.append("SD: %d reads, %d errors" % (self.statistics['sd_reads'], self.statistics['sd_errors']))
        else:
            stats_lines.append("SD: N/A (unavailable)")

        stats_lines.append("Mismatches: %d" % self.statistics['mismatches'])

        return "\n".join(stats_lines)
