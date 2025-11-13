# Stress Test Core
# Main StressTest class using modular components

import asyncio
import time
import gc
from gui.screens.screen import Screen

from .utils import get_memory_info, format_duration
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

        # Find QR host and initialize component testers
        self.qr_host = self.get_existing_qr_host()
        self.qr_tester = QRTester(qr_host=self.qr_host)
        self.smartcard_tester = SmartcardTester()
        self.storage_tester = StorageTester()
        self.sdcard_tester = SDCardTester()

        # Test state
        self.initial_values = {}
        self.test_results = {}
        self.running = False
        self.start_time = None
        self.stats_update_callback = None

        # Configuration
        self.sleep_duration_ms = 0  # Default 0ms - hardware I/O provides natural delay

        # Component enable/disable states (all enabled by default)
        self.component_enabled = {
            'qr_scanner': True,
            'smartcard': False,  # Disabled by default (was commented out)
            'storage': True,
            'sdcard': True
        }

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

    def set_sleep_duration(self, duration_ms):
        """Set the sleep duration between test iterations in milliseconds"""
        if duration_ms < 0:  # Minimum 0ms
            duration_ms = 0
        elif duration_ms > 10000:  # Maximum 10 seconds
            duration_ms = 10000
        self.sleep_duration_ms = duration_ms
        print("Sleep duration set to " + str(duration_ms) + "ms")

    def get_sleep_duration(self):
        """Get the current sleep duration in milliseconds"""
        return self.sleep_duration_ms

    def set_component_enabled(self, component_name, enabled):
        """Enable or disable a specific component for testing

        Args:
            component_name: One of 'qr_scanner', 'smartcard', 'storage', 'sdcard'
            enabled: True to enable, False to disable
        """
        if component_name in self.component_enabled:
            self.component_enabled[component_name] = enabled
            print("Component", component_name, "set to", "enabled" if enabled else "disabled")
        else:
            print("WARNING: Unknown component name:", component_name)

    def get_component_enabled(self, component_name):
        """Check if a component is enabled for testing

        Args:
            component_name: One of 'qr_scanner', 'smartcard', 'storage', 'sdcard'

        Returns:
            True if enabled, False if disabled
        """
        return self.component_enabled.get(component_name, False)

    def get_all_component_states(self):
        """Get the enabled/disabled state of all components

        Returns:
            Dictionary with component names as keys and enabled state as values
        """
        return self.component_enabled.copy()

    async def initialize(self):
        """Initialize all test components"""
        print("=== STRESS TEST INITIALIZATION ===")
        self.start_time = time.time()

        # Initialize each component (with component key for enable/disable check)
        components = [
            ("QR Scanner", "qr_scanner", self.qr_tester),
            ("Smartcard", "smartcard", self.smartcard_tester),
            ("Internal Storage", "storage", self.storage_tester),
            ("SD Card", "sdcard", self.sdcard_tester)
        ]

        for name, component_key, tester in components:
            # Skip if component is disabled
            if not self.component_enabled.get(component_key, False):
                print(name, "is disabled - skipping initialization")
                self.initial_values[name.lower().replace(" ", "_")] = False
                continue

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



        print("=== INITIALIZATION COMPLETE ===")
        print("Available components:")
        for name, component_key, tester in components:
            if not self.component_enabled.get(component_key, False):
                print("  [DISABLED]", name)
            else:
                status = "✓" if tester.is_available() else "✗"
                print(" ", status, name + ":", tester.get_status())
    





    

    

    
    async def run_component_tests(self):
        """Run basic component functionality tests"""
        components = [
            ("qr_scanner", self.qr_tester),
            ("smartcard", self.smartcard_tester),
            ("storage", self.storage_tester),
            ("sdcard", self.sdcard_tester)
        ]

        for name, tester in components:
            if not self.running:
                break

            # Skip if component is disabled
            if not self.component_enabled.get(name, False):
                self.test_results[name] = {"status": "skipped", "reason": "disabled"}
                continue

            if tester.is_available():
                try:
                    result = {"status": "available", "component": name}
                    self.test_results[name] = result
                except Exception as e:
                    self.test_results[name] = {"status": "failed", "error": str(e)}
            else:
                self.test_results[name] = {"status": "skipped", "reason": "not available"}

            await asyncio.sleep_ms(100)
    

    
    async def run_continuous_test(self):
        """Run continuous stress test until stopped"""

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

                # Test each enabled component
                if self.component_enabled.get('qr_scanner', False):
                    await self._test_component_continuously('qr_scanner', self.qr_tester)
                if self.component_enabled.get('smartcard', False):
                    await self._test_component_continuously('smartcard', self.smartcard_tester)
                if self.component_enabled.get('storage', False):
                    await self._test_component_continuously('storage', self.storage_tester)
                if self.component_enabled.get('sdcard', False):
                    await self._test_component_continuously('sdcard', self.sdcard_tester)



                # Call the callback if provided (for GUI updates)
                if self.stats_update_callback:
                    try:
                        stats_text = self.format_statistics_text()
                        self.stats_update_callback(stats_text)
                    except Exception as e:
                        print("Stats callback error:", str(e))

                # Brief pause between iterations - break into 100ms chunks to allow responsive stopping
                remaining_sleep = self.sleep_duration_ms
                while remaining_sleep > 0 and self.running:
                    sleep_chunk = min(100, remaining_sleep)
                    await asyncio.sleep_ms(sleep_chunk)
                    remaining_sleep -= sleep_chunk

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
                    current_data = await tester._read_smartcard()
                    print("Smartcard read:", repr(current_data))
                    self.statistics['smartcard_reads'] += 1

                    # Compare with initial value (like original stress test)
                    if current_data != self.initial_values.get('smartcard'):
                        self.statistics['mismatches'] += 1

                except Exception as e:
                    self.statistics['smartcard_errors'] += 1
                    print("Smartcard read error:", str(e))

            elif component_name == 'storage':
                # Check if storage was successfully initialized
                if not self.initial_values.get('internal_storage'):
                    return

                # Use the actual initial data from the tester
                initial_value = tester.initial_data
                if initial_value is None:
                    return

                try:
                    current_data = await tester._read_storage()
                    self.statistics['storage_reads'] += 1

                    # Compare with initial value (like original stress test)
                    if current_data != initial_value:
                        self.statistics['mismatches'] += 1

                except Exception as e:
                    self.statistics['storage_errors'] += 1
                    print("Storage read error:", str(e))

            elif component_name == 'sdcard':
                print("DEBUG: Testing SD card component")
                # Check if SD card was successfully initialized
                if not self.initial_values.get('sd_card'):
                    print("DEBUG: SD card not initialized, skipping")
                    return

                # Use the actual initial data from the tester
                initial_value = tester.initial_data
                if initial_value is None:
                    print("DEBUG: SD card initial data is None, skipping")
                    return

                print("DEBUG: SD card initial data:", repr(initial_value))
                try:
                    current_data = await tester._read_sdcard()
                    self.statistics['sdcard_reads'] += 1
                    print("DEBUG: SD card read successful, count now:", self.statistics['sdcard_reads'])

                    # Compare with initial value (like original stress test)
                    if current_data != initial_value:
                        self.statistics['mismatches'] += 1
                        print("DEBUG: SD card data mismatch - expected:", repr(initial_value), "got:", repr(current_data))

                except Exception as e:
                    self.statistics['sdcard_errors'] += 1
                    print("SD card read error:", str(e))

        except Exception as e:
            print("Component test error for", component_name + ":", str(e))



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
                ('QR Scanner', 'qr', 'qr_scanner', self.qr_tester),
                ('Smartcard', 'smartcard', 'smartcard', self.smartcard_tester),
                ('Storage', 'storage', 'storage', self.storage_tester),
                ('SD Card', 'sdcard', 'sdcard', self.sdcard_tester)
            ]

            for name, key, component_key, tester in components:
                if not self.component_enabled.get(component_key, False):
                    lines.append(name + ": Disabled")
                elif tester.is_available():
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
    

