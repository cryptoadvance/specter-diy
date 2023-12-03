from unittest import TestCase
from keystore import FlashKeyStore
import os
import platform

TEST_DIR = "testdir"

def init_keystore(ks):
    platform.maybe_mkdir(ks.path)
    ks.load_secret(ks.path)
    ks.load_state()
    ks.initialized = True

class FlashKeyStoreTest(TestCase):

    def get_keystore(self):
        """Clean up the test folder and create fresh keystore"""
        try:
            platform.delete_recursively(TEST_DIR)
            os.rmdir(TEST_DIR)
        except:
            pass
        FlashKeyStore.path = TEST_DIR
        return FlashKeyStore()

    def test_create_config(self):
        """Test initial config creation"""
        ks = self.get_keystore()
        init_keystore(ks)
        files = [f[0] for f in os.ilistdir(TEST_DIR)]
        self.assertTrue("secret" in files)
        self.assertTrue("pin" in files)
        self.assertEqual(ks.is_pin_set, False)
        self.assertEqual(ks.pin_attempts_left, ks.pin_attempts_max)
        self.assertTrue(ks.pin_attempts_left is not None)

    def test_change_secret(self):
        """Test wipe exception if secret is changed"""
        # create keystore
        ks = self.get_keystore()
        init_keystore(ks)
        files = [f[0] for f in os.ilistdir(TEST_DIR)]
        self.assertTrue("secret" in files)
        self.assertTrue("pin" in files)
        # now change secret value
        with open(TEST_DIR+"/secret", "wb") as f:
            # a different value
            f.write(b"5"*32)
        ks = FlashKeyStore()
        # check it raises
        with self.assertRaises(platform.CriticalErrorWipeImmediately):
            init_keystore(ks)
        # files are deleted
        files = [f[0] for f in os.ilistdir(TEST_DIR)]
        self.assertFalse("secret" in files)
        self.assertFalse("pin" in files)

    def test_change_pin_file(self):
        """Test wipe exception if pin state changed"""
        # create keystore
        ks = self.get_keystore()
        init_keystore(ks)
        # load signed pin state
        with open(TEST_DIR+"/pin", "rb") as f:
            # a different value
            content = f.read()
        # set invalid value
        content = content[1:] + b"1"
        # write new state
        with open(TEST_DIR+"/pin", "wb") as f:
            # a different value
            f.write(content)
        ks = FlashKeyStore()
        # check it raises
        with self.assertRaises(platform.CriticalErrorWipeImmediately):
            init_keystore(ks)
        # files are deleted
        files = [f[0] for f in os.ilistdir(TEST_DIR)]
        self.assertFalse("secret" in files)
        self.assertFalse("pin" in files)
