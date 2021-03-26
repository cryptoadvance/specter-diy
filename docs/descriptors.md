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

## Miniscript

Specter supports miniscript, but doesn't support policy-to-miniscript compilation (because it's way too expensive). We perform some checks on the miniscipt, so only `B` scripts are allowed on the top level and all arguments in sub-miniscripts have to have properties according to the [spec](http://bitcoin.sipa.be/miniscript/).

You can use http://bitcoin.sipa.be/miniscript/ to generate a descriptor from a policy and then import it to the wallet.

For example, a policy "I can spend now, or in 100 days my wife can spend" can be converted into the wallet like so:

Policy: `or(9@pk(xpubA),and(older(14400),pk(B)))` (my key is 9-times more likely)

Miniscript: `or_d(pk(xpubA),and_v(v:pkh(xpubB),older(14400)))`

Descriptor: `wsh(or_d(pk(xpubA),and_v(v:pkh(xpubB),older(14400))))`

As here we don't have any wildcard derivations the default derivations of `/{0,1}/*` will be appended to the xpubs.
