from unittest import TestCase
from .controller import sim

class BasicTest(TestCase):

    def test_sign_psbt(self):
        unsigned = b"cHNidP8BAHECAAAAAQWaIPxj7qSA0cbaKKz5Lk43V/8/FZeQw+IQ2tV6eJnbAAAAAAD9////AgfVTQUAAAAAFgAUUzfXvW1SC/+493dPMkR+9Ua1+7mAlpgAAAAAABYAFCwSoUTerJLG437IpfbWF8DgWx6kAAAAAAABAR8Kl+YFAAAAABYAFC80qhzwClOwVaKRoDp9RfCmmItSIgYDXUnszVTQCZ5DZ2J3x6bUYl1hHaiKXfSb+VF6d5Gnd6UYc8XaClQAAIABAACAAAAAgAEAAAAAAAAAACICAzra7/AYOHv1KHXP0Kgv8paA8ELhUBDLW3FrKXZzZpg2GHPF2gpUAACAAQAAgAAAAIABAAAAAgAAAAAA"
        # confirm signing
        res = sim.query(b"sign "+unsigned, [True])
        # signed tx
        self.assertEqual(res, b"cHNidP8BAHECAAAAAQWaIPxj7qSA0cbaKKz5Lk43V/8/FZeQw+IQ2tV6eJnbAAAAAAD9////AgfVTQUAAAAAFgAUUzfXvW1SC/+493dPMkR+9Ua1+7mAlpgAAAAAABYAFCwSoUTerJLG437IpfbWF8DgWx6kAAAAAAAiAgNdSezNVNAJnkNnYnfHptRiXWEdqIpd9Jv5UXp3kad3pUcwRAIgDf80duROzcio5iPQ/RbThlXHzr2tmqFaIHR1SOMHHT8CIDGUwTINLkmIk6onOGtlFSQYibQfjhIkRxmx1LJa0NNGAQAAAA==")

        # cancel signing
        res = sim.query(b"sign "+unsigned, [False])
        self.assertEqual(res, b"error: User cancelled")

    def test_get_xpub(self):
        res = sim.query(b"fingerprint")
        self.assertEqual(res, b"73c5da0a")
        res = sim.query(b"xpub m/44h/1h/0h")
        self.assertEqual(res, b"xpub6BhcvYN2qwQKRviMKKBTfRcK1RmCTmM7JHsg67r3rwvymhUEt8gPHhnkugQaQ7UN8M5FfhEUfyVuSaK5fQzfUpvAcCxN4bAT9jyySbPGsTs")

    def test_add_wallet(self):
        # and(pk(A),after(100)) -> and_v(v:pk(A),after(100))
        desc = "wsh(and_v(v:pk([73c5da0a/44h/1h/0h]xpub6BhcvYN2qwQKRviMKKBTfRcK1RmCTmM7JHsg67r3rwvymhUEt8gPHhnkugQaQ7UN8M5FfhEUfyVuSaK5fQzfUpvAcCxN4bAT9jyySbPGsTs),after(100))"
        addresses = [
            b"bitcoin:bcrt1qd7mtkvjmm7rlpgjjfv3902h6c749d7xuss0pr6garuq8q2qu9xas5qs39e?index=0",
            b"bitcoin:bcrt1qyrmdmuy0ml7m7fw3834lek6anrx20nrlmh7yvhsulu0dhxvgvkds4n9dq5?index=2"
        ]
        # shouldn't find it before adding a wallet
        for addr in addresses:
            res = sim.query(addr)
            self.assertTrue(b"error: Can't find wallet owning address" in res)

        res = sim.query(f"addwallet timelocked&{desc})".encode(), [True])

        # should find it before adding a wallet
        for addr in addresses:
            res = sim.query(addr,[None])
            self.assertFalse(b"error: Can't find wallet owning address" in res)

