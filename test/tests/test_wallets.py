from unittest import TestCase
from apps.wallets.wallet import Wallet
from embit.descriptor import Key

TEST_DIR = "testdir"

class WalletsTest(TestCase):

    def test_descriptors(self):
        """Test initial config creation"""
        k = "[8cce63f8/84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2/{0,1}/*"
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
            self.assertEqual(str(w.descriptor), desc)

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
            "[8cce63f8]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
        ]
        for k in keys:
            Key.parse(k)

    def test_invalid_keys(self):
        keys = [
            "[8c!e63f8/84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "[84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "tpubDCZWXJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2",
            "tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMX",
        ]
        for k in keys:
            with self.assertRaises(Exception):
                Key.parse(k)
                print(k)

    def test_taptree(self):
        d = "tr([73c5da0a/2/2/2]tpubDCPwGho2toLmdSELZ3o8v1D6RUUK7Y5keCjMyrSfE75aX2Mcx4MNEM6MnXDZR87GQ1ot4YNn2GGtiN5SvM12c6cvYMrt6avwtYNcRab2HFv/<0;1>/*,or_b(pk([73c5da0a/1/2/3]tpubDCpEkdSHkygNaquCRtW8Fuo3TchAXFSWUuYB9aryim58T4CWM9vLgt26uUV5wdtuvbSk7rWmQQCpcYhGjbHiBzWCYXeyRMJ98zSBWekaJJm/<0;1>/*),s:pk([73c5da0a/3/2/1]tpubDDrLDbxjL1d5FK8djVqUjD3xL1gkhaTXTL1rHzEavwA2ss4YpF8Qm82cKN89PEBRYk6JVTZULA872LuFGENTGdNYASDCrXKKZkU86A8HLqA/<0;1>/*)))"
        w = Wallet.parse(d)
        print(w)
