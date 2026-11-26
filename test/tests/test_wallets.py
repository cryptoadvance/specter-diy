from unittest import TestCase
from apps.wallets.wallet import Wallet
from embit.descriptor import Key
from embit.descriptor.errors import DescriptorError
from embit.liquid.descriptor import LDescriptor

TEST_DIR = "testdir"

class WalletsTest(TestCase):

    XPUB = "[8cce63f8/84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2"

    def test_mixed_multipath_sortedmulti(self):
        multipath = self.XPUB + "/<0;1>/*"
        fixed = self.XPUB + "/0/*"
        descriptor = "wsh(sortedmulti(1,%s,%s))" % (multipath, fixed)

        parsed = Wallet.parse(descriptor).descriptor
        self.assertEqual(parsed.num_branches, 2)
        self.assertEqual(str(parsed), descriptor)
        self.assertIn("/0/*", str(parsed.branch(0).keys[0]))
        self.assertIn("/1/*", str(parsed.branch(1).keys[0]))
        self.assertEqual(str(parsed.branch(0).keys[1]), str(parsed.branch(1).keys[1]))
        derived_receive = parsed.derive(7, branch_index=0)
        derived_change = parsed.derive(7, branch_index=1)
        self.assertTrue(str(derived_receive.keys[0].origin).endswith("/0/7"))
        self.assertTrue(str(derived_change.keys[0].origin).endswith("/1/7"))
        self.assertEqual(
            str(derived_receive.keys[1]),
            str(derived_change.keys[1]),
        )

    def test_stored_mixed_multipath_descriptor_loads(self):
        multipath = self.XPUB + "/<0;1>/*"
        fixed = self.XPUB + "/0/*"
        descriptor = "wsh(sortedmulti(1,%s,%s))" % (multipath, fixed)

        class StoredWalletKeyStore:
            def load_aead(self, path):
                if path.endswith("/descriptor"):
                    return None, descriptor.encode()
                return None, b'{"gaps":[20,20],"name":"Stored","unused_recv":0}'

        wallet = Wallet.from_path(TEST_DIR + "/wallet", StoredWalletKeyStore())
        self.assertEqual(str(wallet.descriptor), descriptor)
        self.assertEqual(wallet.descriptor.num_branches, 2)
        self.assertEqual(wallet.name, "Stored")

    def test_mixed_multipath_recovery_miniscript(self):
        multipath = self.XPUB + "/<0;1>/*"
        fixed = self.XPUB + "/0/*"
        descriptor = "wsh(or_d(pk(%s),and_v(v:pk(%s),older(10))))" % (
            multipath,
            fixed,
        )

        parsed = Wallet.parse(descriptor).descriptor
        self.assertEqual(parsed.num_branches, 2)
        self.assertIsNotNone(parsed.derive(7, branch_index=0).script_pubkey())
        self.assertIsNotNone(parsed.derive(7, branch_index=1).script_pubkey())

    def test_unequal_multipath_lengths_still_fail(self):
        two_branches = self.XPUB + "/<0;1>/*"
        three_branches = self.XPUB + "/<0;1;2>/*"
        descriptor = "wsh(sortedmulti(1,%s,%s))" % (
            two_branches,
            three_branches,
        )

        with self.assertRaises(DescriptorError):
            Wallet.parse(descriptor)

    def test_mixed_multipath_liquid_descriptor(self):
        multipath = self.XPUB + "/<0;1>/*"
        fixed = self.XPUB + "/0/*"
        descriptor = "wsh(sortedmulti(1,%s,%s))" % (multipath, fixed)

        parsed = LDescriptor.from_string(descriptor)
        self.assertEqual(parsed.num_branches, 2)
        self.assertEqual(str(parsed), descriptor)

    def test_descriptors(self):
        """Test initial config creation"""
        k = "[8cce63f8/84h/1h/0h]tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2/<0;1>/*"
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
