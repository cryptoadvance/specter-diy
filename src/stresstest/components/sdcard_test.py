# SD Card Stress Test Component

import os
import platform
from ..utils import StressTestError, get_timestamp, safe_file_operation


class SDCardTester:
    """SD Card testing component"""
    
    def __init__(self, test_path="/sd/stresstest"):
        # Convert path to proper simulator path if needed
        self.test_path = platform.fpath(test_path)
        self.initial_data = None
        
    async def initialize(self):
        """Initialize SD card testing"""
        try:
            # Check if SD card is present
            if not platform.sdcard.is_present:
                raise StressTestError("SD card not present")

            # Check if SD card directory exists and is accessible
            sd_path = platform.fpath("/sd")
            try:
                # Try to list the directory to see if it exists and is accessible
                list(os.ilistdir(sd_path))
            except OSError as e:
                try:
                    platform.maybe_mkdir(sd_path)
                except Exception as create_error:
                    raise StressTestError("SD card directory not accessible and cannot create: " + str(create_error))

            # Create test directory
            platform.maybe_mkdir(self.test_path)

            # Test basic file operations
            sdcard_data = await self._test_sdcard_operations()
            self.initial_data = sdcard_data
            return True

        except Exception as e:
            print("WARNING: SD card not available:", str(e))
            self.initial_data = None
            return False
    
    async def _test_sdcard_operations(self):
        """Test basic SD card operations"""
        try:
            # Test file creation
            test_file = self.test_path + "/test_" + get_timestamp() + ".txt"
            test_data = "SD card test data: " + get_timestamp()

            # Write test file
            result = safe_file_operation(self._write_test_file, test_file, test_data)
            if result is None:
                raise StressTestError("Failed to write test file")

            # Read test file
            read_data = safe_file_operation(self._read_test_file, test_file)
            if read_data is None:
                raise StressTestError("Failed to read test file")

            # Compare data
            if read_data != test_data:
                raise StressTestError("Data mismatch: written != read")

            # Clean up
            safe_file_operation(self._delete_test_file, test_file)

            return test_data

        except Exception as e:
            raise StressTestError("SD card test failed: " + str(e))
    
    def _write_test_file(self, filename, data):
        """Write test data to file"""
        with open(filename, 'w') as f:
            f.write(data)
        return True
    
    def _read_test_file(self, filename):
        """Read test data from file"""
        with open(filename, 'r') as f:
            return f.read()

    async def _read_sdcard(self):
        """Read SD card data for continuous stress testing"""
        try:
            # Create a quick test file and read it back
            test_file = self.test_path + "/stress_test_" + get_timestamp() + ".txt"
            test_data = self.initial_data  # Use the initial data for comparison

            # Write and read back the data
            result = safe_file_operation(self._write_test_file, test_file, test_data)
            if result is None:
                raise StressTestError("Failed to write stress test file")

            read_data = safe_file_operation(self._read_test_file, test_file)
            if read_data is None:
                raise StressTestError("Failed to read stress test file")

            # Clean up
            safe_file_operation(self._delete_test_file, test_file)

            return read_data

        except Exception as e:
            raise StressTestError("SD card stress read failed: " + str(e))
    

    
    def _delete_test_file(self, filename):
        """Delete test file"""
        try:
            os.remove(filename)
            return True
        except:
            return False
    

    
    async def test_sdcard_performance(self, iterations=5, data_size=1024):
        """Test SD card performance with multiple operations"""
        if not self.is_available():
            return {"status": "skipped", "reason": "SD card not available"}

        successful_operations = 0

        for i in range(iterations):
            try:
                # Create test data
                test_data = "x" * data_size
                test_file = self.test_path + "/perf_test_" + str(i) + "_" + get_timestamp() + ".txt"

                # Write test
                safe_file_operation(self._write_test_file, test_file, test_data)

                # Read test
                read_data = safe_file_operation(self._read_test_file, test_file)

                # Cleanup
                safe_file_operation(self._delete_test_file, test_file)

                # Verify data integrity
                if read_data == test_data:
                    successful_operations += 1

            except Exception:
                pass  # Count as failed iteration

        return {
            "status": "completed",
            "total_iterations": iterations,
            "successful_operations": successful_operations,
            "success_rate": (successful_operations / iterations) * 100
        }
    
    def is_available(self):
        """Check if SD card is available for testing"""
        return self.initial_data is not None
    
    def get_status(self):
        """Get current SD card status"""
        if self.initial_data is None:
            return "Not available"
        return "Available"
    
    def cleanup(self):
        """Clean up test files and directories"""
        try:
            platform.delete_recursively(self.test_path)
        except Exception:
            pass
