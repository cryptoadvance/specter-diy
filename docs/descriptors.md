# Descriptors support

All normal Bitcoin descriptors work. Aside from that we have a few extensions:


## Multiple branches in descriptors

To save some space in the QR codes we allow adding descriptors with multiple branches in one go. If you want to use `wpkh(xpub/0/*)` for receiving addresses and `wpkh(xpub/1/*)` for change addresses you can combine them in a single descriptor: `wpkh(xpub/{0,1}/*)` - the wallet will treat first index of the `{}` set part as the branch for receiving addresses and the second one as change addresses.

You can also specify more than two branches, and branch indexes can be different for different cosigners, so this descriptor is very weird but totally valid:

```
wsh(sortedmulti(2,xpubA/{22,33,44}/*,xpubB/34/*/{1,8,6},pubkey3))
```

Here for receiving address number 17 the wallet will use the script from `wsh(sortedmulti(2,xpubA/22/17,xpubB/34/17/1,pubkey3))`.

The only requirement is that the number of indexes in all sets is the same (3 in the case above).

## Default derivations

If the descriptor contains master public keys but doesn't contain wildcard derivations, the default derivation `/{0,1}/*` will be added to all extended keys in the descriptor. If at least one of the xpubs has a wildcard derivation the descriptor will not be changed.

The descriptor `wpkh(xpub)` will be converted into `wpkh(xpub/{0,1}/*)`.

## Single-sig wallet types and their derivations

When you create a single-sig wallet from **Master public keys -> ... -> Create
wallet**, the script type you pick fixes the derivation, so the key-origin in
the descriptor always matches the key that actually signs:

| Wallet type   | Descriptor   | Standard derivation                   |
|---------------|--------------|---------------------------------------|
| Legacy        | `pkh()`      | `m/44h/coin_type_h/account_h` (BIP44) |
| Nested Segwit | `sh(wpkh())` | `m/49h/coin_type_h/account_h` (BIP49) |
| Native Segwit | `wpkh()`     | `m/84h/coin_type_h/account_h` (BIP84) |
| Taproot       | `tr()`       | `m/86h/coin_type_h/account_h` (BIP86) |

`coin_type` is always taken from the **active network**, never from the key you
were looking at: `0` on Bitcoin mainnet, `1` on testnet/regtest/signet, and the
network's registered value on Liquid (`1776` on Liquid mainnet, `1` on Liquid
testnet/regtest). The account index is carried over from the displayed key
(element `[2]`, so `m/48h/0h/3h/2h` gives account `3`) or the account selected
in the menu. If the key on screen is not already on the standard path, the
account key is genuinely re-derived from it — the descriptor never carries one
path's key-origin over another path's key.

### Recovering a non-standard wallet

Older Specter DIY versions built the descriptor by wrapping *whatever key was on
screen* in the chosen script, so valid but non-standard wallets exist in the
wild — for example `tr()` over an `m/84h` key, `pkh()` over an `m/84h` key,
`wpkh()` over an `m/48h/.../2h` key, or any script over a custom path.

Fresh wallets never do this. But if you pick a wallet type whose standard path
differs from the key you are viewing, the device offers a choice:

```
<type> derivation
[ Standard <type>            m/<purpose>h/<coin>h/<account>h ]
[ Recover using displayed key   <the path on screen>          ]
```

`Recover using displayed key` wraps the exact displayed key (its full
key-origin path preserved — purpose, coin type, account, and deeper levels such
as BIP48) in the selected script, reproducing the historical wallet
byte-for-byte. It is confirmed with a warning: this derivation is non-standard,
other wallet software may not discover it from the seed alone, and it should
only be used to recover an existing wallet. Cancelling or declining creates
nothing.

The BIP86 fix from issue #393 is a special case of this: from the `m/84h`
"Single key", **Create wallet -> Taproot** offers *Standard Taproot* (re-derives
`m/86h`) and *Recover using displayed key* (`tr(m/84h...)`, the wallet older
firmware would have made). Keep your wallet descriptors/backups so recovery is
never guesswork.

## Miniscript

Specter supports miniscript, but doesn't support policy-to-miniscript compilation (because it's way too expensive). We perform some checks on the miniscipt, so only `B` scripts are allowed on the top level and all arguments in sub-miniscripts have to have properties according to the [spec](http://bitcoin.sipa.be/miniscript/).

You can use http://bitcoin.sipa.be/miniscript/ to generate a descriptor from a policy and then import it to the wallet.

For example, a policy "I can spend now, or in 100 days my wife can spend" can be converted into the wallet like so:

Policy: `or(9@pk(xpubA),and(older(14400),pk(B)))` (my key is 9-times more likely)

Miniscript: `or_d(pk(xpubA),and_v(v:pkh(xpubB),older(14400)))`

Descriptor: `wsh(or_d(pk(xpubA),and_v(v:pkh(xpubB),older(14400))))`

As here we don't have any wildcard derivations the default derivations of `/{0,1}/*` will be appended to the xpubs.
