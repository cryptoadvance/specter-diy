from unittest import TestCase
from .util import get_keystore, get_wallets_app, clear_testdir
from bitcoin.psbt import PSBT
from bitcoin.psbtview import PSBTView
from apps.wallets.wallet import Wallet, WalletError
from io import BytesIO

WALLETS = [
    "cpfp_descriptor&wsh(multi(1,xpub661MyMwAqRbcG9F1VX1rYev3ZsFRQ8XdJYk7rYLiaCfLt3WjVQ5o12SeJHPQEUCC8NmTWFmyejXrp3GWTFQNrXHL7iUXcoRo79VEnmKGYhc/*,xpub6CZFHPW1GiB8YgV7zGpeQDB6mMHZYPQyUaHrM1nMvKMgLxwok4xCtnzjuxQ3p1LHJUkz5i1Y7bRy5fmGrdg8UBVb39XdXNtWWd2wTsNd7T9/*))",
    "deposit_descriptor&wsh(multi(2,xpub661MyMwAqRbcEgaXJWejvvXw2PHvr6ZF5ybqahrCnptM1kTNirjVETa6Ba4oTJz3Uppghzow6pQaGzyPaUVeb7vSufEYRUVMyNKX9PyRxWC/*,xpub6DEzq5DNPx2rPiZJ7wvFhxRKUKDoV1GwjFmFdaxFfbsw9HsHyxc9usoRUMxqJaMrwoXh4apahsGEnjAS4cVCBDgqsx5Groww22AdHbgxVDg/*))",
    "unvault_descriptor&wsh(andor(multi(1,xpub661MyMwAqRbcG9F1VX1rYev3ZsFRQ8XdJYk7rYLiaCfLt3WjVQ5o12SeJHPQEUCC8NmTWFmyejXrp3GWTFQNrXHL7iUXcoRo79VEnmKGYhc/*,xpub6CZFHPW1GiB8YgV7zGpeQDB6mMHZYPQyUaHrM1nMvKMgLxwok4xCtnzjuxQ3p1LHJUkz5i1Y7bRy5fmGrdg8UBVb39XdXNtWWd2wTsNd7T9/*),and_v(v:multi(2,02abe475b199ec3d62fa576faee16a334fdb86ffb26dce75becebaaedf328ac3fe,030f64b922aee2fd597f104bc6cb3b670f1ca2c6c49b1071a1a6c010575d94fe5a),older(3)),thresh(2,pkh(xpub661MyMwAqRbcEgaXJWejvvXw2PHvr6ZF5ybqahrCnptM1kTNirjVETa6Ba4oTJz3Uppghzow6pQaGzyPaUVeb7vSufEYRUVMyNKX9PyRxWC/*),a:pkh(xpub6DEzq5DNPx2rPiZJ7wvFhxRKUKDoV1GwjFmFdaxFfbsw9HsHyxc9usoRUMxqJaMrwoXh4apahsGEnjAS4cVCBDgqsx5Groww22AdHbgxVDg/*))))#0v6kshkd",
    # unvault_descriptor without cosigners and using tpub
    "unvault_descriptor_without_cosigs&wsh(andor(thresh(1,pk(tpubD6NzVbkrYhZ4XcB3kRJVob8bmjMvA2zBuagidVzh7ASY5FyAEtq4nTzx9wHYu5XDQAg7vdFNiF6yX38kTCK8zjVVmFTiQR2YKAqZBTGjnoD/*)),older(10),thresh(2,pkh(tpubD6NzVbkrYhZ4WmzFjvQrp7sDa4ECUxTi9oby8K4FZkd3XCBtEdKwUiQyYJaxiJo5y42gyDWEczrFpozEjeLxMPxjf2WtkfcbpUdfvNnozWF/*),a:pkh(tpubD6NzVbkrYhZ4XyJXPpnkwCpTazWgerTFgXLtVehbPyoNKVFfPgXRcoxLGupEES1tSteVGsJon85AxEzGyWVSxm8LX8bdZsz87GWt585X2wf/*))))#u70luyrn",
]

MNEMONICS = [
    "glue possible carpet youth pepper damp capital wrist wage weird fame drastic story vehicle same",
    "toddler vanish target people solar lens midnight great ability state imitate spot discover swamp park",
    "rapid veteran belt horse evidence wine rabbit price protect foam summer excuse",
]

PSBTS = [
    # emergency tx
    (   # unsigned, signed tx
        "cHNidP8BAF4CAAAAAWxdMAXc2LtoRZ5LZIS5xzBiCcMfDRxDuqljOjadSu6ZAQAAAAD9////AXCWmjsAAAAAIgAgy7Co1PHzwoce0hHQR5RHMS72lSZudTF3bYrNgqLbkDYAAAAAAAEBKwDKmjsAAAAAIgAgslrG3QMtjTKpRrHl3ptzoveYxLV1H4x72eg19U2FZPUBAwSBAAAAAQVHUiEDVCsD4yYHkfSMBmB7mvLabNgt+VS7H3cnZivvwQCZ0H8hAlgt7b9E9GVk5djNsGdTbWDr40zR0YAc/1G7+desKJtDUq4iBgNUKwPjJgeR9IwGYHua8tps2C35VLsfdydmK+/BAJnQfwgMIvXFAAAAAAAA",
        "cHNidP8BAF4CAAAAAWxdMAXc2LtoRZ5LZIS5xzBiCcMfDRxDuqljOjadSu6ZAQAAAAD9////AXCWmjsAAAAAIgAgy7Co1PHzwoce0hHQR5RHMS72lSZudTF3bYrNgqLbkDYAAAAAACICA1QrA+MmB5H0jAZge5ry2mzYLflUux93J2Yr78EAmdB/RzBEAiBZe+5519IIyaStMzEwhtADhy1zcJGjcvJDMc4czrmg3QIgf9i/JJZR7jYatii8Q/K67N/Nr7PvifdMFIwD5bZ0M7qBAAA=",
        [0], # mnemonics that can sign, signed by the first one in the list
        ["deposit_descriptor"], # signing wallets
    ),
    # emergency_unvault_tx
    (
        "cHNidP8BAF4CAAAAAfBtTnKT2ciyQFiNsM+ndFiUsOhgSQbIuIm3hdZMU7a7AAAAAAD9////AYr9mTsAAAAAIgAgy7Co1PHzwoce0hHQR5RHMS72lSZudTF3bYrNgqLbkDYAAAAAAAEBK7hCmjsAAAAAIgAgb2phQajLZoTd4qwrA+t5RfiT0EoT+9+8gnKxE7f2ALIBAwSBAAAAAQXKUSEDQtzABCWiGw3zomghjr/+JYlRWPapkMkFz1bYAPyEX6EhAgKTOrEDfq0KpKeFjG1J1nBeH7O8X2awCRive58A7NUmUq5kdqkUTeFfs5G8hINHgr2lEXGqC1pqmhuIrGt2qRRyqV8ir5obrrhS+alScvjCHZjyZIisbJNSh2dSIQKr5HWxmew9YvpXb67hajNP24b/sm3Odb7Ouq7fMorD/iEDD2S5Iq7i/Vl/EEvGyztnDxyixsSbEHGhpsAQV12U/lpSr1OyaCIGA1QrA+MmB5H0jAZge5ry2mzYLflUux93J2Yr78EAmdB/CAwi9cUAAAAAAAA=",
        "cHNidP8BAF4CAAAAAfBtTnKT2ciyQFiNsM+ndFiUsOhgSQbIuIm3hdZMU7a7AAAAAAD9////AYr9mTsAAAAAIgAgy7Co1PHzwoce0hHQR5RHMS72lSZudTF3bYrNgqLbkDYAAAAAACICA1QrA+MmB5H0jAZge5ry2mzYLflUux93J2Yr78EAmdB/RzBEAiBZALTbnvGA+0JaUF2XSbeZbRbgWJHmJCUonqwPQL5a5QIgPc7ASzdlYR+fQ31xZPzvsuw76UGepmmJI2Q5E9gyIKqBAAA=",
        [0, 1],
        ["unvault_descriptor"],
    ),
    # cancel_tx
    (
        "cHNidP8BAF4CAAAAAfBtTnKT2ciyQFiNsM+ndFiUsOhgSQbIuIm3hdZMU7a7AAAAAAD9////AYr9mTsAAAAAIgAgslrG3QMtjTKpRrHl3ptzoveYxLV1H4x72eg19U2FZPUAAAAAAAEBK7hCmjsAAAAAIgAgb2phQajLZoTd4qwrA+t5RfiT0EoT+9+8gnKxE7f2ALIBAwSBAAAAAQXKUSEDQtzABCWiGw3zomghjr/+JYlRWPapkMkFz1bYAPyEX6EhAgKTOrEDfq0KpKeFjG1J1nBeH7O8X2awCRive58A7NUmUq5kdqkUTeFfs5G8hINHgr2lEXGqC1pqmhuIrGt2qRRyqV8ir5obrrhS+alScvjCHZjyZIisbJNSh2dSIQKr5HWxmew9YvpXb67hajNP24b/sm3Odb7Ouq7fMorD/iEDD2S5Iq7i/Vl/EEvGyztnDxyixsSbEHGhpsAQV12U/lpSr1OyaCIGA1QrA+MmB5H0jAZge5ry2mzYLflUux93J2Yr78EAmdB/CAwi9cUAAAAAAAA=",
        "cHNidP8BAF4CAAAAAfBtTnKT2ciyQFiNsM+ndFiUsOhgSQbIuIm3hdZMU7a7AAAAAAD9////AYr9mTsAAAAAIgAgslrG3QMtjTKpRrHl3ptzoveYxLV1H4x72eg19U2FZPUAAAAAACICA1QrA+MmB5H0jAZge5ry2mzYLflUux93J2Yr78EAmdB/RzBEAiA8rmMXMTlf9+cMZmv4CZZ85Mmrx+XKLczcclVylJlhcwIgWDVSyFW7mXRgbAzh3i7HENutcSa+ZlC7eB/hRX88EkeBAAA=",
        [0, 1],
        ["unvault_descriptor"],
    ),
    # cancel_tx with unvault_descriptor_without_cosigs
    (
        "cHNidP8BAF4CAAAAAeJnSwIQ9BWdLKX8LrkM0VoRlchm6pqjFOpBpLFL2fxOAAAAAAD9////AbRW9wcAAAAAIgAgJMk4bvxMit7yF7KTHK7Rz0iR9JdwUmrVcD1ok7SRAs4AAAAAAAEBK1iS9wcAAAAAIgAgI88K3dsiL1U8Vmg3JLhg6gUnFCXGvTkK+781DS0uewYBAwSBAAAAAQVhIQKm242c21PacXWunfRWSZwk7VablpGPi7Vg8DQ4M9cPCaxRh2R2qRQnDL27yUjb1W8opiZchrMRU7rMU4isa3apFJWb6zI1jM0Z+5Pp/SVULQyNmi98iKxsk1KHZ1qyaCIGAqbbjZzbU9pxda6d9FZJnCTtVpuWkY+LtWDwNDgz1w8JCH4IUSgAAAAAIgYCvsxevQZJyDaSLOinK1TPnb3J195WFj3PcGNos7Wt4wkI5wT/vgAAAAAiBgNhT1Lm/4dL7XHNresMp77aznG0Dz6ARZgsgiL88uRE+wiKZPKpAAAAAAAiAgK+zF69BknINpIs6KcrVM+dvcnX3lYWPc9wY2izta3jCQjnBP++AAAAACICA2FPUub/h0vtcc2t6wynvtrOcbQPPoBFmCyCIvzy5ET7CIpk8qkAAAAAAA==",
        "cHNidP8BAF4CAAAAAeJnSwIQ9BWdLKX8LrkM0VoRlchm6pqjFOpBpLFL2fxOAAAAAAD9////AbRW9wcAAAAAIgAgJMk4bvxMit7yF7KTHK7Rz0iR9JdwUmrVcD1ok7SRAs4AAAAAACICA2FPUub/h0vtcc2t6wynvtrOcbQPPoBFmCyCIvzy5ET7RzBEAiBXdewAkgELBOv1Dp76QoxzuCzXGEzrs/J+r6a8AQ9PWgIgZRfICcrHVKsfqWgVIzIAa60smwdqUe5kfL0QmCpDCtKBAAA=",
        [2],
        ["unvault_descriptor_without_cosigs"],
    ),
]

class RevaultTest(TestCase):

    def test_revault_sign(self):
        """Basic signing of the PSBT"""
        for i, mnemonic in enumerate(MNEMONICS):
            clear_testdir()
            ks = get_keystore(mnemonic=mnemonic, password="")
            wapp = get_wallets_app(ks, 'main')
            # add wallets
            for wdesc in WALLETS:
                w = wapp.manager.parse_wallet(wdesc)
                wapp.manager.add_wallet(w)
            for j, (unsigned, signed, mnemonic_idx, wnames) in enumerate(PSBTS):
                psbt = PSBT.from_string(unsigned)
                s = BytesIO(psbt.to_string().encode())
                # check it can sign b64-psbt
                self.assertTrue(wapp.can_process(s))
                # check it can sign raw psbt
                s = BytesIO(psbt.serialize())
                self.assertTrue(wapp.can_process(s))

                fout = BytesIO()
                wallets, meta = wapp.manager.preprocess_psbt(s, fout)
                # check that we detected wallet and a non-standard sighash
                self.assertEqual([w.name for w in wallets], wnames)
                self.assertEqual([inp.get("label").replace(" (watch-only)", "") for inp in meta["inputs"]], wnames)
                self.assertEqual(meta["inputs"][0].get("sighash"), "ALL | ANYONECANPAY")

                fout.seek(0)
                psbtv = PSBTView.view(fout)

                b = BytesIO()
                if i not in mnemonic_idx:
                    with self.assertRaises(WalletError):
                        sig_count = wapp.manager.sign_psbtview(psbtv, b, wallets, None)
                elif i == mnemonic_idx[0]:
                    sig_count = wapp.manager.sign_psbtview(psbtv, b, wallets, None)
                    self.assertEqual(PSBT.parse(b.getvalue()).to_string(), signed)
