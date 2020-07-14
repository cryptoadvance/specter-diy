from unittest import TestCase
from apps.wallets.wallet import Wallet
from apps.wallets.scripts import DescriptorKey
import os, json
import platform

TEST_DIR = "testdir"

class WalletsTest(TestCase):

    def test_descriptors(self):
        """Test initial config creation"""
        k = "[8cce63f8/84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2"
        descriptors = [
            "wpkh(%s)" % k,
            "sh(wpkh(%s))" % k,
            "wsh(sortedmulti(2,%s,%s,%s))" % (k,k,k),
            "sh(wsh(sortedmulti(2,%s,%s,%s)))" % (k,k,k),
            "wsh(multi(3,%s,%s,%s))" % (k,k,k),
            "sh(wsh(multi(2,%s,%s,%s)))" % (k,k,k),
        ]
        for desc in descriptors:
            w = Wallet.parse(desc)
            self.assertEqual(w.descriptor(), desc)

    def test_invalid_desc(self):
        """Test initial config creation"""
        k = "[8cce63f8/84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2"
        descriptors = [
            "wqkh(%s)" % k,
            "(wpkh(%s))" % k,
            "wsh(sortedmulti(2,%s,%s,%s)" % (k,k,k),
            "wsh(sortedmulti(2,%s,%s,%s)))" % (k,k,k),
            "wsh(multi(4,%s,%s,%s))" % (k,k,k),
            "sh(wsh(multi(0,%s,%s,%s)))" % (k,k,k),
        ]
        for desc in descriptors:
            with self.assertRaises(Exception):
                w = Wallet.parse(desc)
                print(w, desc)

    def test_key(self):
        keys = [
            "[8cce63f8/84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "[m/84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "[8cce63f8]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
        ]
        for k in keys:
            DescriptorKey.parse(k)

    def test_invalid_keys(self):
        keys = [
            "[8c!e63f8/84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "[84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "tpubDCZWXJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMX",
        ]
        for k in keys:
            with self.assertRaises(Exception):
                DescriptorKey.parse(k)
                print(k)

