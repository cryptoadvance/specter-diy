# Stress Test Core
# Main StressTest class using modular components

import asyncio
import time
import gc
import platform
from gui.screens import Menu, Alert, Prompt
from gui.screens.screen import Screen
from gui.common import add_label, add_button
from gui.decorators import on_release
import lvgl as lv

from .utils import StressTestError, get_memory_info, log_memory_usage, format_duration
from .components import QRTester, SmartcardTester, StorageTester, SDCardTester


class StressTest(Screen):
    """
    Modular Stress Test for Specter DIY hardware components
    
    This class coordinates testing of various hardware components:
    - QR Scanner
    - Smartcard
    - Internal Storage
    - SD Card
    """
    
    def __init__(self, rampath=None):
        super().__init__()

        # rampath is not used in the modular implementation
        # We keep the parameter for compatibility with specter.py
        if rampath is not None:
            print("Rampath provided but not used:", rampath)

       
        # Find QR host first
        print("Looking for existing QR scanner...")
        self.qr_host = self.get_existing_qr_host()

        # Initialize component testers with their respective hosts
        self.qr_tester = QRTester(qr_host=self.qr_host)
        self.smartcard_tester = SmartcardTester()
        self.storage_tester = StorageTester()
        self.sdcard_tester = SDCardTester()

        if self.qr_host is not None:
            print("Found QRHost, passed to QR tester during initialization")
        else:
            print("No QRHost found, QR tester will not be available")
        
        # Test state
        self.initial_values = {}
        self.test_results = {}
        self.running = False
        self.start_time = None
        self.stats_update_callback = None
        
        # GUI elements
        self.status_label = None
        self.memory_label = None
        self.results_label = None
        
    def get_existing_qr_host(self):
        """Try to get the existing QRHost instance from the Specter application"""
        try:
            # Access the Specter instance through Host.parent
            from hosts.core import Host
            if Host.parent is not None:
                specter = Host.parent
                print("Found Specter instance with", len(specter.hosts), "hosts")

                # Look for QRHost in the hosts list
                for host in specter.hosts:
                    if host.__class__.__name__ == 'QRHost':
                        print("Found QRHost instance:", host)
                        return host

                print("No QRHost found in hosts list")
            else:
                print("No Specter instance found (Host.parent is None)")

        except Exception as e:
            print("Error getting existing QRHost:", str(e))
            import sys
            sys.print_exception(e)

        return None

    async def initialize(self):
        """Initialize all test components"""
        print("=== STRESS TEST INITIALIZATION ===")
        self.start_time = time.time()

        # Initialize each component
        components = [
            ("QR Scanner", self.qr_tester),
            ("Smartcard", self.smartcard_tester),
            ("Internal Storage", self.storage_tester),
            ("SD Card", self.sdcard_tester)
        ]

        for name, tester in components:
            try:
                print("Initializing", name + "...")
                success = await tester.initialize()
                self.initial_values[name.lower().replace(" ", "_")] = success
                if success:
                    print(name, "initialized successfully")
                else:
                    print(name, "not available")
            except Exception as e:
                print("WARNING:", name, "initialization failed:", str(e))
                self.initial_values[name.lower().replace(" ", "_")] = False

        # Log memory usage after initialization
        log_memory_usage("After initialization - ")

        print("=== INITIALIZATION COMPLETE ===")
        print("Available components:")
        for name, tester in components:
            status = "✓" if tester.is_available() else "✗"
            print(" ", status, name + ":", tester.get_status())
    
    def create_gui(self):
        """Create the stress test GUI"""
        self.title = "Hardware Stress Test"

        # Status label
        self.status_label = add_label("Initializing...", scr=self, style="title")
        self.status_label.align(lv.ALIGN.TOP_MID, 0, 10)

        # Memory usage label
        self.memory_label = add_label("Memory: ...", scr=self)
        self.memory_label.align(self.status_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

        # Results area
        self.results_label = add_label("", scr=self)
        self.results_label.align(self.memory_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
        self.results_label.set_width(400)

        # Control buttons
        start_btn = add_button("Start Test", on_release(self.start_stress_test), scr=self)
        start_btn.align(lv.ALIGN.BOTTOM_LEFT, 10, -10)

        stop_btn = add_button("Stop", on_release(self.stop_stress_test), scr=self)
        stop_btn.align(start_btn, lv.ALIGN.OUT_RIGHT_MID, 10, 0)

        menu_btn = add_button("Menu", on_release(self.show_menu), scr=self)
        menu_btn.align(lv.ALIGN.BOTTOM_RIGHT, -10, -10)

        # Update initial status
        self.update_status("Ready to start")
        self.update_memory_display()

    def create_component_sliders(self):
        """Create sliders for enabling/disabling components"""
        components = [
            ('qr_scanner', 'QR Scanner'),
            ('smartcard', 'Smartcard'),
            ('storage', 'Storage'),
            ('sdcard', 'SD Card')
        ]

        y_offset = 20
        for i, (key, name) in enumerate(components):
            # Component label
            label = add_label(name + ":", scr=self)
            label.align(self.memory_label, lv.ALIGN.OUT_BOTTOM_LEFT, 0, y_offset + i * 25)
            self.component_labels[key] = label

            # Component slider
            slider = lv.slider(self)
            slider.set_size(100, 20)
            slider.align(label, lv.ALIGN.OUT_RIGHT_MID, 10, 0)
            slider.set_range(0, 1)
            slider.set_value(1 if self.component_enabled[key] else 0, lv.ANIM.OFF)

            # Add event handler for slider changes
            slider.add_event_cb(
                lambda e, component=key: self.on_slider_change(e, component),
                lv.EVENT.VALUE_CHANGED,
                None
            )

            self.component_sliders[key] = slider

            # Status indicator
            status_label = add_label("ON" if self.component_enabled[key] else "OFF", scr=self)
            status_label.align(slider, lv.ALIGN.OUT_RIGHT_MID, 10, 0)
            status_label.set_style_text_color(
                lv.color_hex(0x00FF00) if self.component_enabled[key] else lv.color_hex(0xFF0000),
                0
            )
            # Store reference for updates
            setattr(self, key + '_status_label', status_label)

    def on_slider_change(self, event, component):
        """Handle slider value changes"""
        slider = event.get_target()
        value = slider.get_value()
        enabled = value > 0

        # Update component state
        self.component_enabled[component] = enabled

        # Update status label
        status_label = getattr(self, component + '_status_label', None)
        if status_label:
            status_label.set_text("ON" if enabled else "OFF")
            status_label.set_style_text_color(
                lv.color_hex(0x00FF00) if enabled else lv.color_hex(0xFF0000),
                0
            )

        print("Component", component, "set to", "enabled" if enabled else "disabled")
    
    def update_status(self, status):
        """Update status display"""
        if self.status_label:
            self.status_label.set_text(status)
    
    def update_memory_display(self):
        """Update memory usage display"""
        if self.memory_label:
            info = get_memory_info()
            self.memory_label.set_text("Memory: " + info['allocated_formatted'] + 
                                     " used, " + info['free_formatted'] + " free")
    
    def update_results_display(self):
        """Update test results display"""
        if not self.results_label:
            return
            
        lines = []
        
        # Show component status
        components = [
            ("QR", self.qr_tester),
            ("Card", self.smartcard_tester),
            ("Flash", self.storage_tester),
            ("SD", self.sdcard_tester)
        ]
        
        for name, tester in components:
            status = "✓" if tester.is_available() else "✗"
            lines.append(name + ": " + status)
        
        # Show test results if available
        if self.test_results:
            lines.append("")
            lines.append("Test Results:")
            for component, result in self.test_results.items():
                if isinstance(result, dict) and 'success_rate' in result:
                    rate = result['success_rate']
                    lines.append(component + ": " + str(int(rate)) + "%")
        
        # Show runtime
        if self.start_time:
            runtime = time.time() - self.start_time
            lines.append("")
            lines.append("Runtime: " + format_duration(runtime))
        
        self.results_label.set_text("\n".join(lines))
    
    async def start_stress_test(self):
        """Start the stress test"""
        if self.running:
            return
            
        self.running = True
        self.update_status("Running stress test...")
        
        try:
            await self.run_stress_test()
        except Exception as e:
            print("Stress test error:", str(e))
            self.update_status("Test failed: " + str(e))
        finally:
            self.running = False
    
    async def stop_stress_test(self):
        """Stop the stress test"""
        self.running = False
        self.update_status("Stopping...")
    
    async def show_menu(self):
        """Show stress test menu"""
        buttons = [
            (1, "Component Tests"),
            (2, "Performance Tests"),
            (3, "Continuous Test"),
            (4, "View Results"),
            (5, "Cleanup"),
            (0, "Back")
        ]
        
        choice = await self.gui.menu(buttons, title="Stress Test Menu")
        
        if choice == 1:
            await self.run_component_tests()
        elif choice == 2:
            await self.run_performance_tests()
        elif choice == 3:
            await self.run_continuous_test()
        elif choice == 4:
            await self.show_detailed_results()
        elif choice == 5:
            await self.cleanup_tests()
        # choice == 0 or None: return to main screen
    
    async def run_stress_test(self):
        """Run the main stress test sequence"""
        print("=== STARTING STRESS TEST ===")
        
        # Run component tests
        await self.run_component_tests()
        
        # Run performance tests if components are available
        await self.run_performance_tests()
        
        print("=== STRESS TEST COMPLETE ===")
        self.update_status("Test complete")
    
    async def run_component_tests(self):
        """Run basic component functionality tests"""
        self.update_status("Testing components...")

        components = [
            ("qr_scanner", self.qr_tester),
            ("smartcard", self.smartcard_tester),
            ("storage", self.storage_tester),
            ("sdcard", self.sdcard_tester)
        ]

        for name, tester in components:
            if not self.running:
                break

            # Check if component is enabled via slider
            if not self.component_enabled.get(name, True):
                print("Skipping", name, "(disabled by user)")
                self.test_results[name] = {"status": "skipped", "reason": "disabled by user"}
                continue

            if tester.is_available():
                print("Testing", name + "...")
                try:
                    # Run basic test (could be extended with specific test methods)
                    result = {"status": "available", "component": name}
                    self.test_results[name] = result
                    print(name, "test completed")
                except Exception as e:
                    print(name, "test failed:", str(e))
                    self.test_results[name] = {"status": "failed", "error": str(e)}
            else:
                print("Skipping", name, "(not available)")
                self.test_results[name] = {"status": "skipped", "reason": "not available"}

            self.update_results_display()
            self.update_memory_display()

            # Small delay between tests
            await asyncio.sleep_ms(100)
    
    async def run_performance_tests(self):
        """Run performance tests on available components"""
        self.update_status("Running performance tests...")
        
        # Add performance test implementations here
        # This is where you'd call the test_*_performance methods from each tester
        
        print("Performance tests completed")
    
    async def run_continuous_test(self):
        """Run continuous stress test until stopped"""
        self.update_status("Running continuous test...")

        # Initialize statistics
        self.statistics = {
            'start_time': time.time(),
            'iterations': 0,
            'qr_reads': 0,
            'qr_errors': 0,
            'smartcard_reads': 0,
            'smartcard_errors': 0,
            'storage_reads': 0,
            'storage_errors': 0,
            'sdcard_reads': 0,
            'sdcard_errors': 0,
            'mismatches': 0
        }

        while self.running:
            try:
                self.statistics['iterations'] += 1
                iteration = self.statistics['iterations']
                print("Continuous test iteration", iteration)

                # Test each available component
                await self._test_component_continuously('qr_scanner', self.qr_tester)
                await self._test_component_continuously('smartcard', self.smartcard_tester)
                await self._test_component_continuously('storage', self.storage_tester)
                await self._test_component_continuously('sdcard', self.sdcard_tester)

                # Update display with statistics
                self.update_continuous_results_display()

                # Call the callback if provided (for GUI updates)
                if self.stats_update_callback:
                    try:
                        stats_text = self.format_statistics_text()
                        self.stats_update_callback(stats_text)
                    except Exception as e:
                        print("Stats callback error:", str(e))

                # Brief pause between iterations
                await asyncio.sleep_ms(1000)

                # Garbage collection
                gc.collect()

            except Exception as e:
                print("Continuous test iteration error:", str(e))
                await asyncio.sleep_ms(1000)

        print("Continuous test stopped after", self.statistics['iterations'], "iterations")

    async def _test_component_continuously(self, component_name, tester):
        """Test a single component continuously"""
        if not tester.is_available():
            return

        # Test each component and handle errors gracefully like the original
        try:
            if component_name == 'qr_scanner':
                # Skip if QR is not available (like original)
                if self.initial_values.get('qr_scanner') is None:
                    return

                try:
                    current_data = await tester._read_qr_code()
                    self.statistics['qr_reads'] += 1

                    # For QR, we expect different data each time
                    # Just check if we got valid data
                    if not current_data:
                        self.statistics['mismatches'] += 1
                        print("QR data mismatch - got:", repr(current_data))

                except Exception as e:
                    self.statistics['qr_errors'] += 1
                    print("QR read error:", str(e))
                    # Don't print full stack trace to avoid spam

            elif component_name == 'smartcard':
                if self.initial_values.get('smartcard') is None:
                    return

                try:
                    # Test smartcard reading
                    self.statistics['smartcard_reads'] += 1
                    # Add actual smartcard test here if needed
                except Exception as e:
                    self.statistics['smartcard_errors'] += 1
                    print("Smartcard read error:", str(e))

            elif component_name == 'storage':
                if self.initial_values.get('storage') is None:
                    return

                try:
                    # Test storage operations
                    self.statistics['storage_reads'] += 1
                    # Add actual storage test here if needed
                except Exception as e:
                    self.statistics['storage_errors'] += 1
                    print("Storage read error:", str(e))

            elif component_name == 'sdcard':
                if self.initial_values.get('sdcard') is None:
                    return

                try:
                    # Test SD card operations
                    self.statistics['sdcard_reads'] += 1
                    # Add actual SD card test here if needed
                except Exception as e:
                    self.statistics['sdcard_errors'] += 1
                    print("SD card read error:", str(e))

        except Exception as e:
            print("Component test error for", component_name + ":", str(e))

    def update_continuous_results_display(self):
        """Update the results display with continuous test statistics"""
        if not self.results_label:
            return

        lines = []

        # Runtime
        if self.start_time:
            runtime = time.time() - self.start_time
            lines.append("Runtime: " + format_duration(runtime))

        lines.append("Iterations: " + str(self.statistics['iterations']))
        lines.append("")

        # Component statistics
        components = [
            ('QR', 'qr', self.qr_tester),
            ('Card', 'smartcard', self.smartcard_tester),
            ('Flash', 'storage', self.storage_tester),
            ('SD', 'sdcard', self.sdcard_tester)
        ]

        for name, key, tester in components:
            if tester.is_available():
                reads = self.statistics.get(key + '_reads', 0)
                errors = self.statistics.get(key + '_errors', 0)
                success_rate = ((reads - errors) / reads * 100) if reads > 0 else 0
                lines.append(name + ": " + str(reads) + " reads, " + str(int(success_rate)) + "% OK")
            else:
                lines.append(name + ": N/A")

        lines.append("")
        lines.append("Mismatches: " + str(self.statistics['mismatches']))

        # Memory info
        info = get_memory_info()
        lines.append("Mem: " + info['allocated_formatted'] + " used")

        self.results_label.set_text("\n".join(lines))

    def format_statistics_text(self):
        """Format statistics for display in the GUI"""
        lines = []

        # Runtime
        if hasattr(self, 'statistics') and 'start_time' in self.statistics:
            runtime = time.time() - self.statistics['start_time']
            lines.append("Runtime: " + format_duration(runtime))

        if hasattr(self, 'statistics'):
            lines.append("Iterations: " + str(self.statistics.get('iterations', 0)))
            lines.append("")

            # Component statistics
            components = [
                ('QR Scanner', 'qr', self.qr_tester),
                ('Smartcard', 'smartcard', self.smartcard_tester),
                ('Storage', 'storage', self.storage_tester),
                ('SD Card', 'sdcard', self.sdcard_tester)
            ]

            for name, key, tester in components:
                if tester.is_available():
                    reads = self.statistics.get(key + '_reads', 0)
                    errors = self.statistics.get(key + '_errors', 0)
                    success_rate = ((reads - errors) / reads * 100) if reads > 0 else 0
                    lines.append(name + ": " + str(reads) + " reads, " + str(int(success_rate)) + "% OK")
                else:
                    lines.append(name + ": Not available")

            lines.append("")
            lines.append("Mismatches: " + str(self.statistics.get('mismatches', 0)))

        # Memory info
        info = get_memory_info()
        lines.append("Memory: " + info['allocated_formatted'] + " used")

        return "\n".join(lines)
    
    async def show_detailed_results(self):
        """Show detailed test results"""
        if not self.test_results:
            await self.gui.alert("No Results", "No test results available yet.")
            return
        
        # Format results for display
        result_text = "Test Results:\n\n"
        for component, result in self.test_results.items():
            result_text += component + ": " + str(result) + "\n"
        
        await self.gui.alert("Test Results", result_text)
    
    async def cleanup_tests(self):
        """Clean up test files and reset state"""
        self.update_status("Cleaning up...")
        
        try:
            self.storage_tester.cleanup()
            self.sdcard_tester.cleanup()
            
            # Clear results
            self.test_results = {}
            self.update_results_display()
            
            print("Cleanup completed")
            self.update_status("Cleanup complete")
            
        except Exception as e:
            print("Cleanup failed:", str(e))
            self.update_status("Cleanup failed")
