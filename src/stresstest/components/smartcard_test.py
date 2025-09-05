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
            
            # Try to read some basic info from the card
            print("Smartcard read: Reading card info...")
            
            # This is a basic test - just check if we can communicate
            # In a real stress test, you might want to read specific data
            card_info = {
                "connection_type": str(type(connection)),
                "timestamp": get_timestamp(),
                "status": "connected"
            }
            
            print("Smartcard read: Success")
            return card_info
            
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
