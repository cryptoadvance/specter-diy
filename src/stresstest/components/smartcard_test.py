# Smartcard Stress Test Component

import time
import sys
from ..utils import StressTestError, get_timestamp


class SmartcardTester:
    """Smartcard testing component"""
    
    def __init__(self):
        self.initial_data = None
        
    async def initialize(self):
        """Initialize smartcard testing"""
        try:
            print("Reading initial smartcard data...")
            smartcard_data = await self._read_smartcard()
            self.initial_data = smartcard_data
            print("Smartcard data:", repr(smartcard_data))
            return True
            
        except Exception as e:
            print("WARNING: Smartcard not available:", str(e))
            self.initial_data = None
            return False
    
    async def _read_smartcard(self):
        """Read data from smartcard"""
        try:
            print("Smartcard read: Starting...")
            
            # Import smartcard utilities
            from keystore.javacard.util import get_connection
            
            # Try to get smartcard connection
            print("Smartcard read: Getting connection...")
            connection = get_connection()

            if connection is None:
                raise StressTestError("No smartcard connection available")

            # Check if card is inserted
            if not connection.isCardInserted():
                raise StressTestError("Smartcard not inserted")

            # Try to connect only if not already connected
            print("Smartcard read: Checking connection status...")
            try:
                # Try to get ATR first - if connection is already established, this should work
                atr = connection.getATR()
                if atr is not None:
                    print("Smartcard read: Using existing connection")
                else:
                    # No ATR available, need to connect
                    print("Smartcard read: Connecting to card...")
                    connection.connect(connection.T1_protocol)
                    atr = connection.getATR()
            except Exception as e:
                if "already connected" in str(e):
                    # Connection already exists, just get the ATR
                    print("Smartcard read: Connection already established")
                    atr = connection.getATR()
                else:
                    # Some other connection error
                    raise e

            print("Smartcard read: Reading ATR...")
            if atr is None:
                raise StressTestError("Could not get ATR from smartcard")

            print("Smartcard read: Success")
            return str(atr)
            
        except Exception as e:
            print("Smartcard read: Exception occurred:", str(e))
            sys.print_exception(e)
            raise StressTestError("Smartcard read failed: " + str(e))
    
    async def test_smartcard_operations(self, iterations=5):
        """Test smartcard operations multiple times"""
        results = []
        successful_reads = 0
        
        for i in range(iterations):
            try:
                print("Smartcard test iteration", i + 1, "of", iterations)
                start_time = time.time()
                
                data = await self._read_smartcard()
                
                end_time = time.time()
                duration = end_time - start_time
                
                results.append({
                    "iteration": i + 1,
                    "status": "success",
                    "duration": duration,
                    "data": data
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
        """Check if smartcard is available for testing"""
        return self.initial_data is not None
    
    def get_status(self):
        """Get current smartcard status"""
        if self.initial_data is None:
            return "Not available"
        return "Available"
