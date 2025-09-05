# Stress Test Module
# Main entry point for the stress test functionality

from .core import StressTest
from .utils import StressTestError

# Export main classes for easy import
__all__ = ['StressTest', 'StressTestError']

# Version info
__version__ = '1.0.0'
