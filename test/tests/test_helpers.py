from unittest import TestCase
from helpers import conv_time

class HelpersTest(TestCase):
    def test_conv_time(self):
        """Test conv_time function: used for converting nLocktime to human-readable timestamp"""
        self.assertEqual(conv_time(0), (1970, 1, 1, 0, 0, 0, 3, 1))
        # Test day before USA DST start on March 7th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1772841600 + hour * 3600), (2026, 3, 7, hour, 0, 0, 5, 66))
        # Test during USA DST start on March 8th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1772928000 + hour * 3600), (2026, 3, 8, hour, 0, 0, 6, 67))
        # Test day after USA DST start on March 9th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1773014400 + hour * 3600), (2026, 3, 9, hour, 0, 0, 0, 68))
        # Test during Europe DST start on March 29th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1774742400 + hour * 3600), (2026, 3, 29, hour, 0, 0, 6, 88))
        # Test during Europe DST end on October 25th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1792886400 + hour * 3600), (2026, 10, 25, hour, 0, 0, 6, 298))
        # Test day before USA DST end on October 31st 2026
        for hour in range(24):
            self.assertEqual(conv_time(1793404800 + hour * 3600), (2026, 10, 31, hour, 0, 0, 5, 304))
        # Test day during USA DST end on November 1st 2026
        for hour in range(24):
            self.assertEqual(conv_time(1793491200 + hour * 3600), (2026, 11, 1, hour, 0, 0, 6, 305))
        # Test day after USA DST end on November 2nd 2026
        for hour in range(24):
            self.assertEqual(conv_time(1793577600 + hour * 3600), (2026, 11, 2, hour, 0, 0, 0, 306))
