from unittest import TestCase
from .util import get_keystore, get_wallets_app, clear_testdir
from bitcoin.liquid.networks import NETWORKS
from bitcoin.liquid.pset import PSET
from bitcoin.psbt import PSBT
from bitcoin.psbtview import PSBTView
from io import BytesIO

PSBTS = {
    # type: (unsigned, signed)
    "wpkh": (
        "cHNidP8BAHECAAAAAWzGfenb3RfMnjMnbG3ma7oQc2hXxtwJfVVmgrnWm+4UAQAAAAD9////AtYbLAQAAAAAFgAUrNujDLwLZgayRWvplXj9l9JCeCWAlpgAAAAAABYAFCwSoUTerJLG437IpfbWF8DgWx6kAAAAAAABAHECAAAAAYWnVTba+0vAveezgcq1RYQ/kgJWaR18whFlaiyB21+IAQAAAAD9////AoCWmAAAAAAAFgAULBKhRN6sksbjfsil9tYXwOBbHqTkssQEAAAAABYAFB8nluuilYNXa/NkD0Yl26S/P0uNAAAAAAEBH+SyxAQAAAAAFgAUHyeW66KVg1dr82QPRiXbpL8/S40iBgIaiZEUrL8SsjMa8kjotFVJqjhEQ9YTjOUqkhEyemGmNhj7fB8RVAAAgAEAAIAAAACAAQAAAAIAAAAAIgID2bmiDcc2vHCuHg7T/C0YXLPanHBaS665367wqdHd9AgY+3wfEVQAAIABAACAAAAAgAEAAAAEAAAAAAA=",
        "cHNidP8BAHECAAAAAWzGfenb3RfMnjMnbG3ma7oQc2hXxtwJfVVmgrnWm+4UAQAAAAD9////AtYbLAQAAAAAFgAUrNujDLwLZgayRWvplXj9l9JCeCWAlpgAAAAAABYAFCwSoUTerJLG437IpfbWF8DgWx6kAAAAAAAiAgIaiZEUrL8SsjMa8kjotFVJqjhEQ9YTjOUqkhEyemGmNkcwRAIgNOT0EGYtB5Qk/sbVAJ0PDZzDcRekwbrayYYUrl3UNgwCIB0hXw26uT9UkyfUSHnSoRJmBi1XZxOYKhH30TrAUi8NAQAAAA=="
    ),
    "sh-wpkh": (
        "cHNidP8BAHICAAAAAWBIbAlD3qho0taVR9yfW3WJwbKcYRv/xyk9I+abUvlCAQAAAAD9////AkBLTAAAAAAAFgAUb6AWUAo8anN+uyYOLdyni6kjRViZSkwAAAAAABepFHnJuo6ORHutCRGwIDdTRBY6M8EuhwAAAAAAAQByAgAAAAHVQM5/vQoGMhr7e/PH4p2Tf9gXHVPtHJfiO1EqDWQMngEAAAAA/v///wJ9xOAKAAAAABYAFNxjOYrYgc0vzoyl79Z63hqrE3QBgJaYAAAAAAAXqRQ8MfB0SM8tY2KH5v3Ga0t2tM7ooIcAAAAAAQEggJaYAAAAAAAXqRQ8MfB0SM8tY2KH5v3Ga0t2tM7ooIcBBBYAFK6BTdJzSK7KokJmZ1fjLTNWu8qjIgYDioMVrQaIBFMr18KKVcfo+ceMcVxDLl97yc2tXBbAHI8Y+3wfETEAAIABAACAAAAAgAAAAAAAAAAAAAABABYAFFUnXeVBP1OyELX2i5VjTnCna9PLIgICrnKgjc/Cy02bVPD8jfANnmyDUdVA78RKcxyHA+zIRy4Y+3wfETEAAIABAACAAAAAgAEAAAAAAAAAAA==",
        "",
    ),
}

PSETS = {
    "wpkh": ("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","")
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

        fout = BytesIO()
        wallets, meta = wapp.manager.preprocess_psbt(s, fout)

        # found a wallet
        self.assertEqual(len(wallets), 1)
        self.assertTrue(wapp.manager.wallets[0] in wallets)

        fout.seek(0)
        psbtv = PSBTView.view(fout)

        b = BytesIO()
        sig_count = wapp.manager.sign_psbtview(psbtv, b, wallets, None)
        self.assertEqual(PSBT.parse(b.getvalue()).to_string(), signed)

    def test_pset(self):
        clear_testdir()
        return
        mnemonic = "ceiling retire saddle forest engine address fancy option fruit destroy grid strategy"
        ks = get_keystore(mnemonic=mnemonic, password="")
        wapp = get_wallets_app(ks, 'elementsregtest')
        # at this stage only wpkh wallet exists
        # so this tx be parsed and signed just fine
        unsigned, signed = PSETS["wpkh"]
        psbt = PSET.from_string(unsigned)
        for inp in psbt.inputs:
            if inp.range_proof:
                inp.asset = None
                inp.value = None
                inp.asset_blinding_factor = None
                inp.value_blinding_factor = None
        s = BytesIO(psbt.to_string().encode())
        # check it can sign b64-psbt
        self.assertTrue(wapp.can_process(s))
        # check it can sign raw psbt
        s = BytesIO(psbt.serialize())
        self.assertTrue(wapp.can_process(s))

        fout = BytesIO()
        psbtv, wallets, meta, sighash = wapp.manager.preprocess_psbt(s, fout)
        import json
        print([o["change"] for o in meta['outputs']])
