# Communcation with the host

## QR codes

### Address verification

To verify receiving address hardware wallet expects the following string:

```
bitcoin:<address>?index=<index>
```

Prefix `bitcoin:` is optional. Index should be the last index of the derivation path for one of existing wallet descriptors. 

Specter tries to derive an address for descriptors of all existing wallets and displays the address on the screen if one of derived addresses matches.

For example, if Specter has two wallets:

- Simple with descriptor `wpkh([b317ec86/84h/1h/0h]vpub5YHLPnkkpPW1ecL7Di7Gv2wDHDtBNqRdt17gMULpxJ27ZA1MmW7xbZjdg1S7d5JKaJ8CiZEmRUHrEB6CGuLomA6ioVa1Pcke6fEb5CzDBU1/_)`
- Multisig with descriptor `wsh(sortedmulti(2,[b317ec86/48h/1h/0h/2h]tpubDEToKMGFhyuP6kfwvjtYaf56khzS1cUcwc47C6aMH6bQ8sNVLMcCK6jr21YDCkU2QhTK5CAnddhfgZ8dD4EL1wGCaAKZaGFeVVdXHaJMTMn,[f04828fe/48h/1h/0h/2h]tpubDFekS5zvPSdW6WWjH2p7vPRkxmeeNGnirmj36AUyoAYbJvfKBj6UARWR5gQ6FRrr98dzT1XFTi6rfGo9AAAeutY1S6SoWijQ8BKxDhYQzDR,[d3c05b2e/48h/1h/0h/2h]tpubDFnAczXQTHxuBh7FxrpLDHBidkC1Di54pTPSPMu4AQjKziFQQTTEFXEVugqm8ucKQhJfLGesBjRZWtLpqAkAmecoXtvaPwCzf4teqrY7Uu5))`

and it scanned QR code with data `bitcoin:bcrt1qd3mtrhysk3k4w6fmu7ayjvwk6q98c2dpf0p4x87zauu8rcgq5dzq73tyrx?index=2`

it will try to derive receiving addresses for both wallets replacing `/_` with `/0/2`. In this case for Multisig wallet the address will match, therefore it will display to the user this address with a title `Address #3 from wallet "Multisig"`. It uses `index+1` in the title as normal people start counting from 1, not from 0.

*Note that wallets are defined for particular network, so if you have a multisig wallet on regtest doesn't mean that it exists on testnet as well, and Specter only checks wallets in currently selected network.*

### Adding wallet to Specter

In order to sign transaction or verify an address Specter needs to know about corresponding wallet. By default only `wpkh` wallet is created for each network, so all multisig wallets need to be imported.

To import the wallet using QR codes user needs to get to the **Wallets** menu and click on **Add wallet**. Scanned QR code should be of the following form:

```
<wallet_name>&<wallet_descriptor>
```

Descriptors used in Specter are almost the same as in [Bitcoin Core](https://github.com/bitcoin/bitcoin/blob/master/doc/descriptors.md) with one exception - we use suffix `/_` to denote derivation paths `/0/*` for receiving and `/1/*` for change addresses.

Example of the multisig wallet import code:

```
My multisig&wsh(sortedmulti(2,[b317ec86/48h/1h/0h/2h]tpubDEToKMGFhyuP6kfwvjtYaf56khzS1cUcwc47C6aMH6bQ8sNVLMcCK6jr21YDCkU2QhTK5CAnddhfgZ8dD4EL1wGCaAKZaGFeVVdXHaJMTMn,[f04828fe/48h/1h/0h/2h]tpubDFekS5zvPSdW6WWjH2p7vPRkxmeeNGnirmj36AUyoAYbJvfKBj6UARWR5gQ6FRrr98dzT1XFTi6rfGo9AAAeutY1S6SoWijQ8BKxDhYQzDR,[d3c05b2e/48h/1h/0h/2h]tpubDFnAczXQTHxuBh7FxrpLDHBidkC1Di54pTPSPMu4AQjKziFQQTTEFXEVugqm8ucKQhJfLGesBjRZWtLpqAkAmecoXtvaPwCzf4teqrY7Uu5))
```

It will promt the user and then create a wallet called "My multisig" with 2 of 3 multisig policy with sorted public keys.

### Signing transaction

Just display a base64-encoded PSBT transaction as a QR code.

We also added one special case for bip32 derivations - if fingerprint in derivation is set to `00000000` it is replaced by the fingerprint of the device. We treat this fingerprint as a mark from software wallet that it doesn't know the fingerprint of the device.

In this case PSBT transaction can be constructed with a correct derivation path even if fingerprint is not known to the software wallet, but the derivation path is known - for example when `zpub` or `ypub` is imported software wallet knows the depth of the derivation (normally `3`), purpose (`84` for `zpub` and `49` for `ypub`), coin type (`0` - Mainnet for `zpub` and `ypub`, `1` - Testnet for `upub` or `vpub`) and master key child number. So `zpub` and `ypub` normally contain full derivation path of the key without master fingerprint.

Signed transaction is also displayed as a base64-encoded PSBT transaction with all unnecessary fields removed - only global transaction and partial signatures for all inputs remain there. All other fields are removed to save space in the QR code. This means that software wallet needs to keep original PSBT and combine them when signed PSBT is scanned.

## USB communication

We use human-readable plain text messages, because we can and they are way easier to debug even though they are not optimal in sense of space. Each command should end with `\r` or `\r\n`.

The following commands are supported:

- `fingerprint` - returns hex fingerprint of the root key.
- `xpub <derivation>` - returns xpub with derivation. For hardened derivation both `h` and `'` can be used. For example `xpub m/84h/1h/0h`.
- `sign <psbt>` - asks user to confirm transaction signing.
- `showaddr <type> <derivation>` - show address of `type` with `derivation`. `type` can be `wpkh`, `sh-wpkh` or `pkh`.
- `importwallet <wallet_name>&<descriptor>` - asks user to confirm adding new `wallet` with `descriptor`.
