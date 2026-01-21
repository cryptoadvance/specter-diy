# QR Scanner Stress Test Component

import time
import sys
from ..utils import StressTestError, get_timestamp


class QRTester:
    """QR Scanner testing component"""
    
    def __init__(self, qr_host=None):
        self.qr_host = qr_host
        self.initial_data = None
        
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
            sys.print_exception(e)
            
        return None
    
    async def initialize(self):
        """Initialize QR scanner testing"""
        try:
            # QR host should be passed during construction
            if self.qr_host is not None:
                print("Using provided QRHost instance")
                print("QRHost path:", self.qr_host.path)
                print("QRHost enabled:", self.qr_host.enabled)
                print("QRHost initialized:", self.qr_host.initialized)

                # Make sure the QRHost is enabled and initialized
                if not self.qr_host.initialized:
                    print("QRHost not initialized, calling init()...")
                    self.qr_host.init()

                if not self.qr_host.enabled:
                    print("QRHost not enabled, enabling...")
                    await self.qr_host.enable()

                # IMPORTANT: Read initial QR code data - this is required!
                # The stress test assumes there's always something to scan initially
                print("Reading initial QR data...")
                print("Please scan a QR code to initialize the stress test...")
                qr_data = await self._read_qr_code()
                self.initial_data = qr_data
                print("QR data:", repr(qr_data))
                return True
            else:
                print("No QRHost instance provided")
                self.initial_data = None
                return False

        except Exception as e:
            print("WARNING: QR scanner not available:", str(e))
            sys.print_exception(e)
            self.initial_data = None
            return False
    
    async def _read_qr_code(self):
        """Read data from QR code for stress testing"""
        try:
            print("QR read: Starting...")
            if self.qr_host is None:
                raise StressTestError("QR host not initialized")

            # Get data from QR scanner with a short timeout for stress testing
            print("QR read: Getting data from QR host...")
            
            # Use a shorter chunk_timeout for stress testing
            stream = await self.qr_host.get_data(raw=True, chunk_timeout=0.1)
            
            if stream is None:
                raise StressTestError("No QR data received")
                
            # Read the data from the stream
            data = stream.read()
            stream.close()
            
            # Convert bytes to string if needed
            if isinstance(data, bytes):
                try:
                    data = data.decode('utf-8')
                except:
                    # If it's not valid UTF-8, keep as bytes representation
                    data = str(data)
            
            print("QR read: Received data:", repr(data))
            return data

        except OSError as e:
            # Check for ENOENT error (file not found) in different ways
            error_str = str(e)
            if "ENOENT" in error_str or "[Errno 2]" in error_str or hasattr(e, 'errno') and e.errno == 2:
                print("QR read: File not found (ENOENT) - this is normal during stress testing")
                raise StressTestError("QR read timeout - no data available")
            else:
                print("QR read: OS Error:", error_str)
                raise StressTestError("QR read OS error: " + error_str)
        except Exception as e:
            print("QR read: Exception occurred:", str(e))
            sys.print_exception(e)
            raise StressTestError("QR read failed: " + str(e))
    
    async def test_qr_scanning(self, iterations=5):
        """Test QR scanning multiple times"""
        if self.qr_host is None:
            return {"status": "skipped", "reason": "QR host not available"}
        
        results = []
        successful_reads = 0
        
        for i in range(iterations):
            try:
                print("QR test iteration", i + 1, "of", iterations)
                start_time = time.time()
                
                data = await self._read_qr_code()
                
                end_time = time.time()
                duration = end_time - start_time
                
                results.append({
                    "iteration": i + 1,
                    "status": "success",
                    "data_length": len(data) if data else 0,
                    "duration": duration
                })
                successful_reads += 1
                
            except Exception as e:
                results.append({
                    "iteration": i + 1,
                    "status": "failed",
                    "error": str(e)
                })
        
        return {
            "status": "completed",
            "total_iterations": iterations,
            "successful_reads": successful_reads,
            "success_rate": (successful_reads / iterations) * 100,
            "results": results
        }
    
    def is_available(self):
        """Check if QR scanner is available for testing"""
        return self.qr_host is not None
    
    def get_status(self):
        """Get current QR scanner status"""
        if self.qr_host is None:
            return "Not available"
        
        status_parts = []
        if hasattr(self.qr_host, 'enabled') and self.qr_host.enabled:
            status_parts.append("Enabled")
        if hasattr(self.qr_host, 'initialized') and self.qr_host.initialized:
            status_parts.append("Initialized")
        
        return ", ".join(status_parts) if status_parts else "Available"
