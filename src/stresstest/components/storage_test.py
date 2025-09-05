# Internal Storage Stress Test Component

import time
import os
import gc
import platform
from ..utils import StressTestError, get_timestamp, format_bytes, safe_file_operation


class StorageTester:
    """Internal storage testing component"""
    
    def __init__(self, test_path="/flash/stresstest"):
        self.test_path = test_path
        self.initial_data = None
        
    async def initialize(self):
        """Initialize storage testing"""
        try:
            print("Testing internal storage...")
            
            # Create test directory
            platform.maybe_mkdir(self.test_path)
            
            # Test basic file operations
            storage_data = await self._test_storage_operations()
            self.initial_data = storage_data
            print("Storage test completed:", repr(storage_data))
            return True
            
        except Exception as e:
            print("WARNING: Internal storage not available:", str(e))
            self.initial_data = None
            return False
    
    async def _test_storage_operations(self):
        """Test basic storage operations"""
        try:
            print("Storage test: Starting...")
            
            # Test file creation
            test_file = self.test_path + "/test_" + get_timestamp() + ".txt"
            test_data = "Storage test data: " + get_timestamp()
            
            print("Storage test: Writing file...")
            result = safe_file_operation(self._write_test_file, test_file, test_data)
            if result is None:
                raise StressTestError("Failed to write test file")
            
            print("Storage test: Reading file...")
            read_data = safe_file_operation(self._read_test_file, test_file)
            if read_data is None:
                raise StressTestError("Failed to read test file")
            
            if read_data != test_data:
                raise StressTestError("Data mismatch: written != read")
            
            print("Storage test: Checking file stats...")
            file_size = safe_file_operation(self._get_file_size, test_file)
            
            print("Storage test: Cleaning up...")
            safe_file_operation(self._delete_test_file, test_file)
            
            # Get storage info
            storage_info = self._get_storage_info()
            
            result = {
                "test_file": test_file,
                "data_length": len(test_data),
                "file_size": file_size,
                "storage_info": storage_info,
                "timestamp": get_timestamp(),
                "status": "success"
            }
            
            print("Storage test: Success")
            return result
            
        except Exception as e:
            print("Storage test: Exception occurred:", str(e))
            raise StressTestError("Storage test failed: " + str(e))
    
    def _write_test_file(self, filename, data):
        """Write test data to file"""
        with open(filename, 'w') as f:
            f.write(data)
        return True
    
    def _read_test_file(self, filename):
        """Read test data from file"""
        with open(filename, 'r') as f:
            return f.read()
    
    def _get_file_size(self, filename):
        """Get file size"""
        try:
            stat = os.stat(filename)
            return stat[6]  # Size is at index 6 in MicroPython
        except:
            return None
    
    def _delete_test_file(self, filename):
        """Delete test file"""
        try:
            os.remove(filename)
            return True
        except:
            return False
    
    def _get_storage_info(self):
        """Get storage information"""
        try:
            # Get filesystem stats
            if hasattr(os, 'statvfs'):
                stats = os.statvfs('/flash')
                block_size = stats[0]
                total_blocks = stats[2]
                free_blocks = stats[3]
                
                total_space = block_size * total_blocks
                free_space = block_size * free_blocks
                used_space = total_space - free_space
                
                return {
                    "total_space": total_space,
                    "free_space": free_space,
                    "used_space": used_space,
                    "total_formatted": format_bytes(total_space),
                    "free_formatted": format_bytes(free_space),
                    "used_formatted": format_bytes(used_space)
                }
            else:
                return {"status": "statvfs not available"}
        except Exception as e:
            return {"error": str(e)}
    
    async def test_storage_performance(self, iterations=5, data_size=1024):
        """Test storage performance with multiple operations"""
        results = []
        successful_operations = 0
        
        for i in range(iterations):
            try:
                print("Storage test iteration", i + 1, "of", iterations)
                start_time = time.time()
                
                # Create test data
                test_data = "x" * data_size
                test_file = self.test_path + "/perf_test_" + str(i) + "_" + get_timestamp() + ".txt"
                
                # Write test
                write_start = time.time()
                safe_file_operation(self._write_test_file, test_file, test_data)
                write_time = time.time() - write_start
                
                # Read test
                read_start = time.time()
                read_data = safe_file_operation(self._read_test_file, test_file)
                read_time = time.time() - read_start
                
                # Cleanup
                safe_file_operation(self._delete_test_file, test_file)
                
                end_time = time.time()
                total_duration = end_time - start_time
                
                # Verify data integrity
                data_ok = (read_data == test_data) if read_data else False
                
                results.append({
                    "iteration": i + 1,
                    "status": "success" if data_ok else "data_error",
                    "data_size": data_size,
                    "write_time": write_time,
                    "read_time": read_time,
                    "total_duration": total_duration,
                    "data_integrity": data_ok
                })
                
                if data_ok:
                    successful_operations += 1
                
            except Exception as e:
                results.append({
                    "iteration": i + 1,
                    "status": "failed",
                    "error": str(e)
                })
        
        return {
            "status": "completed",
            "total_iterations": iterations,
            "successful_operations": successful_operations,
            "success_rate": (successful_operations / iterations) * 100,
            "data_size": data_size,
            "results": results
        }
    
    def is_available(self):
        """Check if storage is available for testing"""
        return self.initial_data is not None
    
    def get_status(self):
        """Get current storage status"""
        if self.initial_data is None:
            return "Not available"
        return "Available"
    
    def cleanup(self):
        """Clean up test files and directories"""
        try:
            platform.delete_recursively(self.test_path)
            print("Storage test cleanup completed")
        except Exception as e:
            print("Storage cleanup failed:", str(e))
