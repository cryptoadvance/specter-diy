import hmac
from unittest import TestCase
from unittest.mock import patch

import keystore.flash as flash_module
import platform
from helpers import tagged_hash
from keystore.core import PinError
from keystore.flash import FlashKeyStore


CORRECT_PIN = "1234"
WRONG_PIN = "0000"


class InMemoryFlashKeyStore(FlashKeyStore):
    """Small persistence/wipe double for the PIN state-machine tests."""

    def __init__(self, state=None):
        super().__init__()
        self.state = {} if state is None else state
        self.wipe_calls = 0
        self.wipe_error = None

    def save_state(self):
        self.state.update(
            pin=self.pin,
            pin_attempts_max=self._pin_attempts_max,
            pin_attempts_left=self._pin_attempts_left,
        )

    def load_state(self):
        if self.state:
            self.pin = self.state["pin"]
            self._pin_attempts_max = self.state["pin_attempts_max"]
            self._pin_attempts_left = self.state["pin_attempts_left"]

    def load_enc_secret(self):
        self.enc_secret = b"encryption secret"

    def wipe(self, path):
        self.wipe_calls += 1
        if self.wipe_error is not None:
            raise self.wipe_error


class FailingLoadStateKeyStore(FlashKeyStore):
    def __init__(self):
        super().__init__()
        self.wipe_calls = 0
        self.wipe_error = None

    def load_aead(self, path, key=None):
        raise RuntimeError("invalid PIN state")

    def wipe(self, path):
        self.wipe_calls += 1
        if self.wipe_error is not None:
            raise self.wipe_error


def configure_pin(keystore, attempts_left=10):
    keystore.secret = b"s" * 32
    keystore.pin = hmac.new(
        tagged_hash("pin", keystore.secret),
        CORRECT_PIN.encode(),
        digestmod="sha256",
    ).digest()
    keystore._pin_attempts_left = attempts_left
    keystore._pin_attempts_max = 10
    keystore._is_locked = True
    keystore.save_state()


class FlashKeyStorePinStateTest(TestCase):
    def test_nine_wrong_pins_leave_one_attempt(self):
        keystore = InMemoryFlashKeyStore()
        configure_pin(keystore)
        for _ in range(9):
            with self.assertRaises(PinError):
                keystore._unlock(WRONG_PIN)
        self.assertEqual(keystore.pin_attempts_left, 1)
        self.assertEqual(keystore.wipe_calls, 0)

    def test_correct_tenth_pin_unlocks_and_resets_counter(self):
        keystore = InMemoryFlashKeyStore()
        configure_pin(keystore)
        for _ in range(9):
            with self.assertRaises(PinError):
                keystore._unlock(WRONG_PIN)
        keystore._unlock(CORRECT_PIN)
        self.assertEqual(keystore.pin_attempts_left, keystore.pin_attempts_max)
        self.assertFalse(keystore.is_locked)
        self.assertEqual(keystore.wipe_calls, 0)

    def test_wrong_tenth_pin_triggers_critical_wipe(self):
        keystore = InMemoryFlashKeyStore()
        configure_pin(keystore)
        for _ in range(9):
            with self.assertRaises(PinError):
                keystore._unlock(WRONG_PIN)
        with self.assertRaises(platform.CriticalErrorWipeImmediately):
            keystore._unlock(WRONG_PIN)
        self.assertEqual(keystore.pin_attempts_left, 0)
        self.assertEqual(keystore.wipe_calls, 1)

    def test_persisted_zero_reboot_skips_pin_verification(self):
        state = {}
        keystore = InMemoryFlashKeyStore(state)
        configure_pin(keystore, attempts_left=0)
        rebooted = InMemoryFlashKeyStore(state)
        rebooted.load_state()
        with patch.object(
            flash_module, "tagged_hash", side_effect=AssertionError("PIN checked")
        ):
            with self.assertRaises(platform.CriticalErrorWipeImmediately):
                rebooted._unlock(CORRECT_PIN)
        self.assertEqual(rebooted.pin_attempts_left, 0)
        self.assertEqual(rebooted.wipe_calls, 1)

    def test_negative_persisted_counter_is_fail_closed(self):
        state = {}
        keystore = InMemoryFlashKeyStore(state)
        configure_pin(keystore, attempts_left=-1)
        rebooted = InMemoryFlashKeyStore(state)
        rebooted.load_state()
        with patch.object(
            flash_module, "tagged_hash", side_effect=AssertionError("PIN checked")
        ):
            with self.assertRaises(platform.CriticalErrorWipeImmediately):
                rebooted._unlock(CORRECT_PIN)
        self.assertEqual(rebooted.pin_attempts_left, -1)
        self.assertEqual(rebooted.wipe_calls, 1)

    def test_failed_local_wipe_still_triggers_critical_wipe(self):
        keystore = InMemoryFlashKeyStore()
        configure_pin(keystore, attempts_left=1)
        keystore.wipe_error = RuntimeError("wipe failed")
        with self.assertRaises(platform.CriticalErrorWipeImmediately):
            keystore._unlock(WRONG_PIN)
        self.assertEqual(keystore.wipe_calls, 1)

    def test_power_cut_after_persisting_zero_cannot_add_attempt(self):
        state = {}
        keystore = InMemoryFlashKeyStore(state)
        configure_pin(keystore, attempts_left=1)
        keystore._pin_attempts_left -= 1
        keystore.save_state()
        rebooted = InMemoryFlashKeyStore(state)
        rebooted.load_state()
        with patch.object(
            flash_module, "tagged_hash", side_effect=AssertionError("PIN checked")
        ):
            with self.assertRaises(platform.CriticalErrorWipeImmediately):
                rebooted._unlock(CORRECT_PIN)
        self.assertEqual(rebooted.pin_attempts_left, 0)

    def test_load_state_wipe_failure_still_triggers_critical_wipe(self):
        keystore = FailingLoadStateKeyStore()
        keystore.path = "testdir"
        keystore.wipe_error = RuntimeError("wipe failed")
        with patch.object(flash_module.platform, "file_exists", return_value=True):
            with self.assertRaises(platform.CriticalErrorWipeImmediately):
                keystore.load_state()
        self.assertEqual(keystore.wipe_calls, 1)
