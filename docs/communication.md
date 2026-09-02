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

- Simple with descriptor `wpkh([b317ec86/84h/1h/0h]vpub5YHLPnkkpPW1ecL7Di7Gv2wDHDtBNqRdt17gMULpxJ27ZA1MmW7xbZjdg1S7d5JKaJ8CiZEmRUHrEB6CGuLomA6ioVa1Pcke6fEb5CzDBU1)`
- Multisig with descriptor `wsh(sortedmulti(2,[b317ec86/48h/1h/0h/2h]tpubDEToKMGFhyuP6kfwvjtYaf56khzS1cUcwc47C6aMH6bQ8sNVLMcCK6jr21YDCkU2QhTK5CAnddhfgZ8dD4EL1wGCaAKZaGFeVVdXHaJMTMn,[f04828fe/48h/1h/0h/2h]tpubDFekS5zvPSdW6WWjH2p7vPRkxmeeNGnirmj36AUyoAYbJvfKBj6UARWR5gQ6FRrr98dzT1XFTi6rfGo9AAAeutY1S6SoWijQ8BKxDhYQzDR,[d3c05b2e/48h/1h/0h/2h]tpubDFnAczXQTHxuBh7FxrpLDHBidkC1Di54pTPSPMu4AQjKziFQQTTEFXEVugqm8ucKQhJfLGesBjRZWtLpqAkAmecoXtvaPwCzf4teqrY7Uu5))`

and it scanned QR code with data `bitcoin:bcrt1qd3mtrhysk3k4w6fmu7ayjvwk6q98c2dpf0p4x87zauu8rcgq5dzq73tyrx?index=2`

it will try to derive receiving addresses for both wallets appending `/0/2` to every descriptor key. In this case for Multisig wallet the address will match, therefore it will display to the user this address with a title `Address #2 from wallet "Multisig"`.

*Note that wallets are defined for particular network, so if you have a multisig wallet on regtest doesn't mean that it exists on testnet as well, and Specter only checks wallets in currently selected network.*

### Adding wallet to Specter

In order to sign transaction or verify an address Specter needs to know about corresponding wallet. By default only `wpkh` wallet is created for each network, so all multisig wallets need to be imported.

To import the wallet using QR codes user needs to get to the **Wallets** menu and click on **Add wallet**. Scanned QR code should be of the following form:

```
addwallet <wallet_name>&<wallet_descriptor>
```

Descriptors used in Specter are almost the same as in [Bitcoin Core](https://github.com/bitcoin/bitcoin/blob/master/doc/descriptors.md) with a few differences - they support miniscript, multiple branches definitions and use default derivations `/{0,1}/*`. Check out [descriptors.md](./descriptors.md) for details.

Example of the multisig wallet import code:

```
addwallet My multisig&wsh(sortedmulti(2,[b317ec86/48h/1h/0h/2h]tpubDEToKMGFhyuP6kfwvjtYaf56khzS1cUcwc47C6aMH6bQ8sNVLMcCK6jr21YDCkU2QhTK5CAnddhfgZ8dD4EL1wGCaAKZaGFeVVdXHaJMTMn,[f04828fe/48h/1h/0h/2h]tpubDFekS5zvPSdW6WWjH2p7vPRkxmeeNGnirmj36AUyoAYbJvfKBj6UARWR5gQ6FRrr98dzT1XFTi6rfGo9AAAeutY1S6SoWijQ8BKxDhYQzDR,[d3c05b2e/48h/1h/0h/2h]tpubDFnAczXQTHxuBh7FxrpLDHBidkC1Di54pTPSPMu4AQjKziFQQTTEFXEVugqm8ucKQhJfLGesBjRZWtLpqAkAmecoXtvaPwCzf4teqrY7Uu5))
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

- `fingerprint` - returns hex fingerprint of the root key. Non-interactive: doesn't require on-device confirmation, so companion software can use it for passive device discovery/identification.
- `xpub <derivation>` - returns xpub with derivation. For hardened derivation both `h` and `'` can be used. For example `xpub m/84h/1h/0h`. Unlike `fingerprint`, this **requires on-device confirmation** by default (see "XPUB privacy" below) - the device shows the requested path and the resulting xpub and waits for Confirm/Cancel. A cancelled request returns `error: User cancelled` without disclosing the xpub.
- `xpubauth begin <scope>` / `xpubauth end` - scoped multi-XPUB authorization, letting a host request one bounded set of paths and then retrieve all of them via plain `xpub <derivation>` calls with a single confirmation. See "Scoped multi-XPUB authorization" below.
- `sign <psbt>` - asks user to confirm transaction signing.
- `showaddr <type> <derivation> [witness_script_hex]` - show address of `type` with `derivation`. `type` can be `wpkh`, `sh-wpkh`, `pkh`, `sh`, `sh-wsh` or `wsh`. Witness script is required for non-pkh wallets.
- `importwallet <wallet_name>&<descriptor>` - asks user to confirm adding new `wallet` with `descriptor`.

### XPUB privacy

Any host connected over USB, or any process on the connected computer that can reach the Specter's serial port, can otherwise ask for wallet public keys and enumerate the wallet's addresses and balance without the user noticing. Because of that, a bare `xpub <derivation>` request always requires a physical Confirm/Cancel on the trusted display, showing exactly the derivation path and the resulting xpub that would be shared. This is deliberately different from hardware wallets that export a fixed set of "standard" xpubs silently - Specter's threat model assumes *any* program on the connected computer, not just the wallet software the user intends to use, may be sending these requests.

Requesting many xpubs this way (e.g. wallet/account discovery, or [BIP-0138](https://github.com/bitcoin/bips/blob/master/bip-0138.mediawiki)-style recovery) would mean one confirmation per key, which is impractical. `xpubauth` (below) solves that without giving up the confirm-by-default privacy property.

### Scoped multi-XPUB authorization

`xpubauth begin <scope>` asks the user to approve, once, a bounded, explicitly enumerated set of derivation paths. After approval, `xpub <derivation>` requests that fall inside the approved scope are answered immediately, without another prompt; anything outside the scope keeps requiring the normal individual confirmation described above. `xpubauth end` discards the authorization explicitly. The host does not have to retrieve every path in the scope - stopping early (e.g. as soon as BIP-138 recovery succeeds) is fine.

This is a logical, per-device-session permission, not tied to any particular transport connection - `xpub` requests over USB/simulator each open and close their own connection, so the authorization is tracked by the firmware itself, in RAM, independently of how many separate connections the host makes.

#### Scope grammar

```
scope     := entry (";" entry)*
entry     := "m" ("/" component)*
component := index | range
index     := digits ["h" | "H" | "'"]
range     := "{" digits "-" digits "}" ["h" | "H" | "'"]
```

- Each entry is either an **exact path** (`m/84h/0h/0h`) or a path with **exactly one bounded range component** (`m/84h/0h/{0-9}h`, `m/48h/0h/{0-9}h/2h`). At most one range per entry.
- A range's two numbers are inclusive, non-negative, non-hardened child indices; a trailing hardening marker (if present) applies to the whole range. There is no open range, no negative range and no wildcard (`*`) of any kind - every scope denotes a finite, precomputable set of paths, and the firmware rejects anything that isn't before displaying or allocating anything for it.
- Multiple entries are separated by `;`, e.g. `m/84h/0h/{0-9}h;m/86h/0h/{0-9}h`.
- Both `h`/`H` and `'` are accepted for hardened components and are equivalent - the device parses every path (both scope entries and later `xpub` requests) into normalized BIP32 integers and matches on that normalized form, never on raw text.
- Duplicate or overlapping entries (e.g. `m/84h/0h/{0-9}h` together with `m/84h/0h/5h`) make the whole `begin` request invalid - overlap is rejected rather than silently merged, so the displayed and enforced count are always identical.
- For recognizable standard purposes (`44h`, `48h`, `49h`, `84h`, `86h`, `87h`), the coin-type component must be a fixed value matching the network active on the device at the time of the request (see "Network binding" below); a scope mixing e.g. a mainnet and a testnet-style entry is rejected as a whole. Non-standard/custom paths carry no such implied network semantics and are left alone.
- Hard limits (named constants in `apps/xpubs/scope.py`): at most 16 entries, at most 8 path components per entry, at most 200 values per range, at most 200 total xpubs per authorization, at most 1024 bytes for the whole `begin` argument. These comfortably cover the ~70-path BIP-138 discovery scope with headroom while keeping worst-case parsing, display and memory use trivial on the STM32F469.
- The raw `xpubauth` payload is capped (`MAX_SCOPE_COMMAND_LEN`) by the command handler as it is read from the host - before it is decoded to text or handed to the parser - so an over-long line is rejected without first being buffered as a Python string. The plain `xpub <derivation>` request is bounded the same way (`MAX_XPUB_PATH_LEN` in `apps/xpubs/xpubs.py`).

Example - the approximate BIP-138 mainnet discovery scope:

```
xpubauth begin m/44h/0h/{0-9}h;m/49h/0h/{0-9}h;m/84h/0h/{0-9}h;m/86h/0h/{0-9}h;m/87h/0h/{0-9}h;m/48h/0h/{0-9}h/1h;m/48h/0h/{0-9}h/2h
```

The device shows the network, the list of allowed path patterns and the maximum possible number of xpubs, then waits for Confirm/Cancel. `success` is returned on confirmation, `error: User cancelled` on cancellation. On cancellation no authorization is left active - not the requested one, and not any authorization that happened to be active before this `begin` (see "When an authorization is cleared").

#### Network binding

An authorization is bound to the exact Specter network (`main`, `test`, `signet`, `regtest`, `liquidv1`, `liquidtestnet`, `elementsregtest`, ...) active when it was approved - not just to a BIP44 coin type, since testnet/signet/regtest all share coin type `1h`. Any network change immediately invalidates the authorization; a subsequent `xpub` request for a formerly-authorized path is treated as unauthorized and falls back to the normal individual confirmation. A single authorization can never cover more than one network.

#### Budget and consumption

Every unique xpub covered by an authorization can be retrieved silently **at most once**. A repeat request for an already-used path is treated like any other out-of-scope request and requires normal confirmation again. Once every path covered by the authorization has been used once, it is discarded automatically (no need to call `xpubauth end`). This keeps the exposure of a stale authorization (e.g. host software crashing mid-recovery while the device stays unlocked) tightly bounded: at most one silent export per authorized path, ever.

#### When an authorization is cleared

An authorization exists only in RAM and is never written to flash, SD card or any settings file - a reboot clears it by construction. It is also cleared, immediately, on:

- `xpubauth end`;
- the device being locked;
- the active network changing;
- a new key/seed being loaded, or the current one being replaced (including a passphrase change);
- every path covered by it having been used once (self-exhaustion, see above);
- the authorization request itself being cancelled, failing validation, or failing to display;
- a new `xpubauth begin` request arriving - the existing authorization is dropped immediately, before the new scope is parsed or displayed, regardless of whether the new request is ultimately approved.

Starting a new `xpubauth begin` while an authorization is already active is **fail-closed**: the existing permission is revoked up front, before the new scope is even parsed. The new scope is then parsed, validated and shown for a fresh confirmation exactly like any other `begin` request, and installed only if that confirmation succeeds. If the new request is cancelled - or malformed - the device is left with **no** authorization at all, never the previous one. A cancelled replacement request therefore cannot silently leave an older, broader permission in force. `begin` never merges, widens or falls back to a prior scope.

#### Compatibility

- Older companion software that has never heard of `xpubauth` keeps working unchanged: it just keeps sending individual `xpub <derivation>` requests, each with its own confirmation, exactly as before this feature existed.
- Newer companion software talking to older firmware that doesn't recognize `xpubauth` gets an `error: ...` response for that command and should fall back to plain per-path `xpub` requests.

## SD card

`.psbt` and `.txt` files are supported. The content of the file is processed like a USB or QR code, so it can be a transaction, wallet import command or address verification command.
