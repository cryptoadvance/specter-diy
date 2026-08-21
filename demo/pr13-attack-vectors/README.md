# Additional change-metadata attack vectors

These fixtures exercise the change-output protections from PR #13 using the
same public test seed as the original demo:

`abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about`

Scan `0_seed_qr_abandon_about.svg` into a fresh device or simulator first.
Then send one of the three PSBT QR codes with the device's `sign` flow. The
base64 PSBT files are included for USB or automated testing.

All amounts and addresses below are the real transaction outputs. A claimed
derivation is host-provided PSBT metadata and is not trusted by itself.

## 1. Forged Taproot change metadata

The input belongs to `Default` at `/0/0`. Output 1 is a real Taproot address,
but Taproot BIP32 metadata falsely claims `Default` branch `/1/7`. The local
descriptor derives a different script.

Expected result:

| Output | Value | Actual address | Detected wallet/derivation | Change | Warning |
|---:|---:|---|---|---|---|
| 0 | 100000 sats | `bcrt1qky3zfexqlcxs2nhrxfum0afhnz8sr2zh3n0y4y` | external | No | none |
| 1 | 50000 sats | `bcrt1ppxmvqneyd4qjke57g4yhyxhesd2nn3durlpyvjww7eqmn0ksx95qwdrm8u` | no wallet; rejected `/1/7` claim | No | invalid change metadata |

Both outputs remain on the primary page and details page. Output 1 shows its
actual Taproot address and the warning:

`Invalid change metadata! Host claimed this output as wallet change, but it does not match your wallet. Verify the destination.`

## 2. Two forged change outputs

The input belongs to `Default` at `/0/0`. Outputs 0 and 1 both carry forged
branch-1 metadata, but neither script matches the locally derived address.
This checks that one warning does not overwrite another output's warning.

Expected result:

| Output | Value | Actual address | Claimed derivation | Change | Warning |
|---:|---:|---|---|---|---|
| 0 | 40000 sats | `bcrt1qyvsy6ypssxmqmdzthzua3qwupkey90p36yq330` | `/1/8` | No | invalid change metadata |
| 1 | 30000 sats | `bcrt1qlhjgdyz385dh07885mre2f3cq6nsgrye4nuehx` | `/1/9` | No | invalid change metadata |
| 2 | 20000 sats | `bcrt1q9eqrj9ulhhe5uwu4gezmgcsjkmmmza8ydasrhk` | external | No | none |

All three outputs remain visible on both pages, with the warning attached to
outputs 0 and 1 separately.

## 3. Unknown input with genuine change

The output really is the `Default` branch `/1/10` address and its script
matches perfectly. The input intentionally has no wallet derivation metadata,
so the input wallet is unknown.

Expected result:

| Output | Value | Actual address | Detected wallet/derivation | Change | Warning |
|---:|---:|---|---|---|---|
| 0 | 50000 sats | `bcrt1q6mpyx6qvvpuhkg0u9fq7ddllh6zrsrpw9thhfg` | `Default` `/1/10` | No | none |

The device first shows its existing `Unknown wallet in inputs!` confirmation.
After continuing, the output remains visible on the primary page and details
page. It must not be hidden merely because the output is genuine change.

## Verification

All three PSBTs were run through the production
`WalletManager.preprocess_psbt()` path on the current PR head. The native
regression suite also passed. A full MicroPython simulator run requires the
repository's Unix build environment (`make unix`); that build tool is not
available on the Windows host used to prepare these fixtures.
