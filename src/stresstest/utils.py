# Stress Test Utilities
# Common utility functions used across stress test components

import time
import gc
import platform


class StressTestError(Exception):
    """Custom exception for stress test errors"""
    pass


def format_bytes(bytes_val):
    """Format bytes into human readable format"""
    if bytes_val < 1024:
        return str(bytes_val) + " B"
    elif bytes_val < 1024 * 1024:
        return str(bytes_val // 1024) + " KB"
    else:
        return str(bytes_val // (1024 * 1024)) + " MB"


def get_memory_info():
    """Get current memory usage information"""
    gc.collect()
    free = gc.mem_free()
    allocated = gc.mem_alloc()
    total = free + allocated
    
    return {
        'free': free,
        'allocated': allocated,
        'total': total,
        'free_formatted': format_bytes(free),
        'allocated_formatted': format_bytes(allocated),
        'total_formatted': format_bytes(total)
    }


def log_memory_usage(prefix=""):
    """Log current memory usage"""
    info = get_memory_info()
    print(prefix + "Memory: " + info['allocated_formatted'] + " used, " + 
          info['free_formatted'] + " free")


def safe_file_operation(operation, *args, **kwargs):
    """Safely perform file operations with error handling"""
    try:
        return operation(*args, **kwargs)
    except Exception as e:
        print("File operation failed:", str(e))
        return None


def cleanup_temp_files(path):
    """Clean up temporary files in the given path"""
    try:
        platform.delete_recursively(path)
        platform.maybe_mkdir(path)
    except Exception as e:
        print("Cleanup failed:", str(e))


def get_timestamp():
    """Get current timestamp as string"""
    return str(time.time())


def format_duration(seconds):
    """Format duration in seconds to human readable format"""
    if seconds < 60:
        return str(int(seconds)) + "s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return str(minutes) + "m " + str(secs) + "s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return str(hours) + "h " + str(minutes) + "m"
