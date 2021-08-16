from unittest import TestCase
from .util import get_keystore, get_wallets_app, clear_testdir
from bitcoin.liquid.networks import NETWORKS
from bitcoin.psbt import PSBT
from bitcoin.psbtview import PSBTView
from io import BytesIO

PSBTS = {
    # type: (unsigned, signed)
    "wpkh": ("cHNidP8BAHECAAAAAWzGfenb3RfMnjMnbG3ma7oQc2hXxtwJfVVmgrnWm+4UAQAAAAD9////AtYbLAQAAAAAFgAUrNujDLwLZgayRWvplXj9l9JCeCWAlpgAAAAAABYAFCwSoUTerJLG437IpfbWF8DgWx6kAAAAAAABAHECAAAAAYWnVTba+0vAveezgcq1RYQ/kgJWaR18whFlaiyB21+IAQAAAAD9////AoCWmAAAAAAAFgAULBKhRN6sksbjfsil9tYXwOBbHqTkssQEAAAAABYAFB8nluuilYNXa/NkD0Yl26S/P0uNAAAAAAEBH+SyxAQAAAAAFgAUHyeW66KVg1dr82QPRiXbpL8/S40iBgIaiZEUrL8SsjMa8kjotFVJqjhEQ9YTjOUqkhEyemGmNhj7fB8RVAAAgAEAAIAAAACAAQAAAAIAAAAAIgID2bmiDcc2vHCuHg7T/C0YXLPanHBaS665367wqdHd9AgY+3wfEVQAAIABAACAAAAAgAEAAAAEAAAAAAA=","cHNidP8BAHECAAAAAWzGfenb3RfMnjMnbG3ma7oQc2hXxtwJfVVmgrnWm+4UAQAAAAD9////AtYbLAQAAAAAFgAUrNujDLwLZgayRWvplXj9l9JCeCWAlpgAAAAAABYAFCwSoUTerJLG437IpfbWF8DgWx6kAAAAAAAiAgIaiZEUrL8SsjMa8kjotFVJqjhEQ9YTjOUqkhEyemGmNkcwRAIgNOT0EGYtB5Qk/sbVAJ0PDZzDcRekwbrayYYUrl3UNgwCIB0hXw26uT9UkyfUSHnSoRJmBi1XZxOYKhH30TrAUi8NAQAAAA=="),
    "sh-wpkh": ("cHNidP8BAHICAAAAAWBIbAlD3qho0taVR9yfW3WJwbKcYRv/xyk9I+abUvlCAQAAAAD9////AkBLTAAAAAAAFgAUb6AWUAo8anN+uyYOLdyni6kjRViZSkwAAAAAABepFHnJuo6ORHutCRGwIDdTRBY6M8EuhwAAAAAAAQByAgAAAAHVQM5/vQoGMhr7e/PH4p2Tf9gXHVPtHJfiO1EqDWQMngEAAAAA/v///wJ9xOAKAAAAABYAFNxjOYrYgc0vzoyl79Z63hqrE3QBgJaYAAAAAAAXqRQ8MfB0SM8tY2KH5v3Ga0t2tM7ooIcAAAAAAQEggJaYAAAAAAAXqRQ8MfB0SM8tY2KH5v3Ga0t2tM7ooIcBBBYAFK6BTdJzSK7KokJmZ1fjLTNWu8qjIgYDioMVrQaIBFMr18KKVcfo+ceMcVxDLl97yc2tXBbAHI8Y+3wfETEAAIABAACAAAAAgAAAAAAAAAAAAAABABYAFFUnXeVBP1OyELX2i5VjTnCna9PLIgICrnKgjc/Cy02bVPD8jfANnmyDUdVA78RKcxyHA+zIRy4Y+3wfETEAAIABAACAAAAAgAEAAAAAAAAAAA==",),
}

class SignTest(TestCase):

    def test_basic(self):
        """Basic signing of the PSBT"""
        clear_testdir()
        ks = get_keystore(mnemonic="ability "*11+"acid", password="")
        wapp = get_wallets_app(ks, 'regtest')
        # at this stage only wpkh wallet exists
        # so this tx be parsed and signed just fine
        unsigned, signed = PSBTS["wpkh"]
        psbt = PSBT.from_string(unsigned)
        s = BytesIO(psbt.to_string().encode())
        # check it can sign b64-psbt
        self.assertTrue(wapp.can_process(s))
        # check it can sign raw psbt
        s = BytesIO(psbt.serialize())
        self.assertTrue(wapp.can_process(s))

        psbtv, wallets, meta, sighash = wapp.preprocess_psbt(s)
        # no warnings for this PSBT
        self.assertEqual(meta["warnings"], [])
        # found a wallet
        self.assertEqual(len(wallets), 1)
        self.assertEqual(wallets[0][0].name, "Default")

        b = BytesIO()
        sig_count = wapp.sign_psbtview(psbtv, b, wallets, sighash)
        self.assertEqual(PSBT.parse(b.getvalue()).to_string(), signed)
