from app import BaseApp
from gui.screens import Menu, InputScreen, Prompt, TransactionScreen
from .screens import WalletScreen, ConfirmWalletScreen

import platform
import os
from binascii import hexlify, unhexlify, a2b_base64
from bitcoin import script, bip32, compact
from bitcoin.psbt import DerivationPath
from bitcoin.psbtview import PSBTView, read_write
from bitcoin.networks import NETWORKS
from bitcoin.transaction import SIGHASH
from .wallet import WalletError, Wallet
from .commands import DELETE, EDIT
from io import BytesIO
from bcur import bcur_decode_stream, bcur_encode_stream
from helpers import a2b_base64_stream, b2a_base64_stream
import gc
import json

SIGN_PSBT = 0x01
ADD_WALLET = 0x02
# verify address from address itself
# and it's index
VERIFY_ADDRESS = 0x03
# show address with certain
# derivation path or descriptor
DERIVE_ADDRESS = 0x04
# sign psbt transaction encoded in bc-ur format
SIGN_BCUR = 0x05
# list wallet names
LIST_WALLETS = 0x06

BASE64_STREAM = 0x64
RAW_STREAM = 0xFF

SIGHASH_NAMES = {
    SIGHASH.ALL: "ALL",
    SIGHASH.NONE: "NONE",
    SIGHASH.SINGLE: "SINGLE",
}
# add sighash | anyonecanpay
for sh in list(SIGHASH_NAMES):
    SIGHASH_NAMES[sh | SIGHASH.ANYONECANPAY] = SIGHASH_NAMES[sh] + " | ANYONECANPAY"

class WalletManager(BaseApp):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    button = "Wallets"
    prefixes = [b"addwallet", b"sign", b"showaddr", b"listwallets"]
    name = "wallets"

    PSBTViewClass = PSBTView
    B64PSBT_PREFIX = b"cHNi"

    def __init__(self, path):
        self.root_path = path
        platform.maybe_mkdir(path)
        self.path = None
        self.wallets = []

    def init(self, keystore, network, *args, **kwargs):
        """Loads or creates default wallets for new keystore or network"""
        super().init(keystore, network, *args, **kwargs)
        self.keystore = keystore
        # add fingerprint dir
        path = self.root_path + "/" + hexlify(self.keystore.fingerprint).decode()
        platform.maybe_mkdir(path)
        if network not in NETWORKS:
            raise WalletError("Invalid network")
        self.network = network
        # add network dir
        path += "/" + network
        platform.maybe_mkdir(path)
        self.path = path
        self.wallets = self.load_wallets()
        if self.wallets is None or len(self.wallets) == 0:
            w = self.create_default_wallet(path=self.path + "/0")
            self.wallets = [w]

    def get_address(self, psbtout):
        """Helper function to get an address for every output"""
        network = NETWORKS[self.network]
        # finally just return bitcoin address or unconfidential
        try:
            return psbtout.script_pubkey.address(network)
        except Exception as e:
            # use hex if script doesn't have address representation
            return hexlify(psbtout.script_pubkey.data).decode()

    async def menu(self, show_screen):
        buttons = [(None, "Your wallets")]
        buttons += [(w, w.name) for w in self.wallets if not w.is_watchonly]
        if len(buttons) != (len(self.wallets)+1):
            buttons += [(None, "Watch only wallets")]
            buttons += [(w, w.name) for w in self.wallets if w.is_watchonly]
        menuitem = await show_screen(Menu(buttons, last=(255, None)))
        if menuitem == 255:
            # we are done
            return False
        else:
            w = menuitem
            # pass wallet and network
            self.show_loader(title="Loading wallet...")
            cmd = await w.show(self.network, show_screen)
            if cmd == DELETE:
                scr = Prompt(
                    "Delete wallet?",
                    'You are deleting wallet "%s".\n'
                    "Are you sure you want to do it?" % w.name,
                )
                conf = await show_screen(scr)
                if conf:
                    self.delete_wallet(w)
            elif cmd == EDIT:
                scr = InputScreen(
                    title="Enter new wallet name",
                    note="",
                    suggestion=w.name,
                    min_length=1, strip=True
                )
                name = await show_screen(scr)
                if name is not None and name != w.name and name != "":
                    w.name = name
                    w.save(self.keystore)
            return True

    def can_process(self, stream):
        cmd, stream = self.parse_stream(stream)
        return cmd is not None

    def parse_stream(self, stream):
        prefix = self.get_prefix(stream)
        # if we have prefix
        if prefix is not None:
            if prefix == b"sign":
                return SIGN_PSBT, stream
            elif prefix == b"showaddr":
                return DERIVE_ADDRESS, stream
            elif prefix == b"addwallet":
                return ADD_WALLET, stream
            elif prefix == b"listwallets":
                return LIST_WALLETS, stream
            else:
                return None, None
        # if not - we get data any without prefix
        # trying to detect type:
        # probably base64-encoded PSBT
        data = stream.read(40)
        if data[:9] == b"UR:BYTES/":
            # rewind
            stream.seek(0)
            return SIGN_BCUR, stream
        if data[:len(self.PSBTViewClass.MAGIC)] == self.PSBTViewClass.MAGIC:
            stream.seek(0)
            return SIGN_PSBT, stream
        if data[:len(self.B64PSBT_PREFIX)] == self.B64PSBT_PREFIX:
            try:
                psbt = a2b_base64(data)
                if psbt[:len(self.PSBTViewClass.MAGIC)] != self.PSBTViewClass.MAGIC:
                    return None, None
                # rewind
                stream.seek(0)
                return SIGN_PSBT, stream
            except:
                pass
        # probably wallet descriptor
        if b"&" in data and b"?" not in data:
            # rewind
            stream.seek(0)
            return ADD_WALLET, stream
        # probably verifying address
        if data.startswith(b"bitcoin:") or data.startswith(b"BITCOIN:") or b"index=" in data:
            if data.startswith(b"bitcoin:") or data.startswith(b"BITCOIN:"):
                stream.seek(8)
            else:
                stream.seek(0)
            return VERIFY_ADDRESS, stream

        return None, None

    async def process_host_command(self, stream, show_screen):
        platform.delete_recursively(self.tempdir)
        cmd, stream = self.parse_stream(stream)
        if cmd == SIGN_PSBT:
            encoding = BASE64_STREAM
            if stream.read(len(self.PSBTViewClass.MAGIC)) == self.PSBTViewClass.MAGIC:
                encoding = RAW_STREAM
            stream.seek(-5, 1)
            res = await self.sign_psbt(stream, show_screen, encoding)
            if res is not None:
                obj = {
                    "title": "Transaction is signed!",
                    "message": "Scan it with your wallet",
                }
                return res, obj
            return
        if cmd == SIGN_BCUR:
            # move to the end of UR:BYTES/
            stream.seek(9, 1)
            # move to the end of hash if it's there
            d = stream.read(70)
            if b"/" in d:
                pos = d.index(b"/")
                stream.seek(pos-len(d)+1, 1)
            else:
                stream.seek(-len(d), 1)
            with open(self.tempdir+"/raw", "wb") as f:
                bcur_decode_stream(stream, f)
            gc.collect()
            with open(self.tempdir+"/raw", "rb") as f:
                res = await self.sign_psbt(f, show_screen, encoding=RAW_STREAM)
            if res is not None:
                # bcur-encode to temp data file
                with open(self.tempdir+"/bcur_data", "wb") as fout:
                    if isinstance(res, str):
                        with open(res, "rb") as fin:
                            l, hsh = bcur_encode_stream(fin, fout, upper=True)
                    else:
                        l, hsh = bcur_encode_stream(res, fout, upper=True)
                # add prefix and hash
                with open(self.tempdir+"/bcur_full", "wb") as fout:
                    fout.write(b"UR:BYTES/")
                    fout.write(hsh)
                    fout.write(b"/")
                    with open(self.tempdir+"/bcur_data", "rb") as fin:
                        b = bytearray(100)
                        while True:
                            l = fin.readinto(b)
                            if l == 0:
                                break
                            fout.write(b, l)
                obj = {
                    "title": "Transaction is signed!",
                    "message": "Scan it with your wallet",
                }
                gc.collect()
                return self.tempdir+"/bcur_full", obj
            return
        elif cmd == LIST_WALLETS:
            wnames = json.dumps([w.name for w in self.wallets])
            return BytesIO(wnames.encode()), {}
        elif cmd == ADD_WALLET:
            # read content, it's small
            desc = stream.read().decode().strip()
            w = self.parse_wallet(desc)
            res = await self.confirm_new_wallet(w, show_screen)
            if res:
                self.add_wallet(w)
            return
        elif cmd == VERIFY_ADDRESS:
            data = stream.read().decode().replace("bitcoin:", "")
            # should be of the form addr?index=N or similar
            if "index=" not in data or "?" not in data:
                raise WalletError("Can't verify address with unknown index")
            addr, rest = data.split("?")
            args = rest.split("&")
            idx = None
            for arg in args:
                if arg.startswith("index="):
                    idx = int(arg[6:])
                    break
            w, _ = self.find_wallet_from_address(addr, index=idx)
            await show_screen(WalletScreen(w, self.network, idx))
            return
        elif cmd == DERIVE_ADDRESS:
            arr = stream.read().split(b" ")
            redeem_script = None
            if len(arr) == 2:
                script_type, path = arr
            elif len(arr) == 3:
                script_type, path, redeem_script = arr
            else:
                raise WalletError("Too many arguments")
            paths = [p.decode() for p in path.split(b",")]
            if len(paths) == 0:
                raise WalletError("Invalid path argument")
            res = await self.showaddr(
                paths, script_type, redeem_script, show_screen=show_screen
            )
            return BytesIO(res), {}
        else:
            raise WalletError("Unknown command")

    async def sign_psbt(self, stream, show_screen, encoding=BASE64_STREAM):
        if encoding == BASE64_STREAM:
            with open(self.tempdir+"/raw", "wb") as f:
                # read in chunks, write to ram file
                a2b_base64_stream(stream, f)
            with open(self.tempdir+"/raw", "rb") as f:
                res = await self.sign_psbt(f, show_screen, encoding=RAW_STREAM)
            if res:
                with open(self.tempdir+"/signed_b64", "wb") as fout:
                    with open(res, "rb") as fin:
                        b2a_base64_stream(fin, fout)
                return self.tempdir+"/signed_b64"
            return

        self.show_loader(title="Parsing transaction...")
        # preprocess stream - parse psbt, check wallets in inputs and outputs,
        # get metadata to display, default sighash for signing,
        # fill missing metadata and store it in temp file:
        with open(self.tempdir + "/filled_psbt", "wb") as fout:
            wallets, meta, sighash = self.preprocess_psbt(stream, fout)
        sighash_name = SIGHASH_NAMES[sighash]
        # now we can work with copletely filled psbt:
        with open(self.tempdir + "/filled_psbt", "rb") as f:
            psbtv = self.PSBTViewClass.view(f)

            # check if there are any custom sighashes
            used_custom_sighashes = any([inp.get("sighash", None) is not None for inp in meta["inputs"]])
            # ask the user if he wants to sign in case of non-default sighashes
            if used_custom_sighashes:
                custom_sighashes = [
                        ("Input %d: %s" % (i, inp.get("sighash", sighash_name)))
                        for (i, inp) in enumerate(meta["inputs"])
                        if inp.get("sighash", sighash_name) != sighash_name
                ]
                canceltxt = (
                    ("Only proceed %s" % SIGHASH_NAMES[sighash])
                    if len(custom_sighashes) != psbtv.num_inputs
                    else "Cancel"
                )
                confirm = await show_screen(Prompt("Warning!",
                    "\nCustom SIGHASH flags are used!\n\n"+"\n".join(custom_sighashes),
                    confirm_text="Proceed anyway", cancel_text=canceltxt
                ))
                if confirm:
                    # we set sighash to None
                    # if we want to use whatever sighash is provided in input
                    sighash = None
                else:
                    # if we are forced to use default sighash - check
                    # that not all inputs have custom sighashes
                    if len(custom_sighashes) == psbtv.num_inputs:
                        # nothing to sign
                        return

            # check if any inputs belong to unknown wallets
            # wallets is a dict: {wallet: amount}
            if None in wallets:
                scr = Prompt(
                    "Warning!",
                    "\nUnknown wallet in inputs!\n\n\n"
                    "The source wallet for some inputs is unknown! This means we can't verify change address.\n\n\n"
                    "Hint:\nYou can cancel this transaction and import the wallet by scanning it's descriptor.\n\n\n"
                    "Proceed to the transaction confirmation?",
                )
                proceed = await show_screen(scr)
                if not proceed:
                    return None

            # build title for the tx screen
            spends = []
            unit = "BTC" if self.network == "main" else "tBTC"
            for w in wallets:
                if w is None:
                    name = "Unknown wallet"
                else:
                    name = w.name
                amount = wallets[w]
                spends.append('%.8f %s\nfrom "%s"' % (amount / 1e8, unit, name))
            title = "Inputs:\n" + "\n".join(spends)
            res = await show_screen(TransactionScreen(title, meta))
            del meta
            gc.collect()
            # sign transaction if the user confirmed
            if res:
                self.show_loader(title="Signing transaction...")
                with open(self.tempdir+"/signed_raw", "wb") as f:
                    sig_count = self.sign_psbtview(psbtv, f, wallets, sighash)
                return self.tempdir+"/signed_raw"

    async def confirm_new_wallet(self, w, show_screen):
        keys = w.get_key_dicts(self.network)
        for k in keys:
            k["mine"] = self.keystore.owns(k["key"])
        if not any([k["mine"] for k in keys]):
            if not await show_screen(
                    Prompt("Warning!",
                           "None of the keys belong to the device.\n\n"
                           "Are you sure you still want to add the wallet?")):
                return False
        return await show_screen(ConfirmWalletScreen(w.name, w.full_policy, keys, w.is_miniscript))

    async def showaddr(
        self, paths: list, script_type: str, redeem_script=None, show_screen=None
    ) -> str:
        net = NETWORKS[self.network]
        if redeem_script is not None:
            redeem_script = script.Script(unhexlify(redeem_script))
        # first check if we have corresponding wallet:
        address = None
        if redeem_script is not None:
            if script_type == b"wsh":
                address = script.p2wsh(redeem_script).address(net)
            elif script_type == b"sh-wsh":
                address = script.p2sh(script.p2wsh(redeem_script)).address(net)
            elif script_type == b"sh":
                address = script.p2sh(redeem_script).address(net)
            else:
                raise WalletError("Unsupported script type: %s" % script_type)

        else:
            if len(paths) != 1:
                raise WalletError("Invalid number of paths, expected 1")
            path = paths[0]
            if not path.startswith("m/"):
                path = "m" + path[8:]
            derivation = bip32.parse_path(path)
            pub = self.keystore.get_xpub(derivation)
            if script_type == b"wpkh":
                address = script.p2wpkh(pub).address(net)
            elif script_type == b"sh-wpkh":
                address = script.p2sh(script.p2wpkh(pub)).address(net)
            elif script_type == b"pkh":
                address = script.p2pkh(pub).address(net)
            else:
                raise WalletError("Unsupported script type: %s" % script_type)

        w, (idx, branch_idx) = self.find_wallet_from_address(address, paths=paths)
        if show_screen is not None:
            await show_screen(
                WalletScreen(w, self.network, idx, branch_index=branch_idx)
            )
        return address

    def load_wallets(self):
        """Loads all wallets from path"""
        try:
            platform.maybe_mkdir(self.path)
            # Get ids of the wallets.
            # Every wallet is stored in a numeric folder
            wallet_ids = sorted(
                [
                    int(f[0])
                    for f in os.ilistdir(self.path)
                    if f[0].isdigit() and f[1] == 0x4000
                ]
            )
            return [self.load_wallet(self.path + ("/%d" % wid)) for wid in wallet_ids]
        except:
            return []

    def load_wallet(self, path):
        """Loads a wallet with particular id"""
        try:
            # pass path and key for verification
            return Wallet.from_path(path, self.keystore)
        except Exception as e:
            # if we failed to load -> delete folder and throw an error
            platform.delete_recursively(path, include_self=True)
            raise e

    def create_default_wallet(self, path):
        """Creates default p2wpkh wallet with name `Default`"""
        der = "m/84h/%dh/0h" % NETWORKS[self.network]["bip32"]
        xpub = self.keystore.get_xpub(der)
        desc = "wpkh([%s%s]%s/{0,1}/*)" % (
            hexlify(self.keystore.fingerprint).decode(),
            der[1:],
            xpub.to_base58(NETWORKS[self.network]["xpub"]),
        )
        w = Wallet.parse("Default&"+desc, path)
        # pass keystore to encrypt data
        w.save(self.keystore)
        platform.sync()
        return w

    def parse_wallet(self, desc):
        try:
            w = Wallet.parse(desc)
        except Exception as e:
            raise WalletError("Can't parse descriptor\n\n%s" % str(e))
        if str(w.descriptor) in [str(ww.descriptor) for ww in self.wallets]:
            raise WalletError("Wallet with this descriptor already exists")
        # check that xpubs and tpubs are not mixed in the same descriptor:
        if not w.check_network(NETWORKS[self.network]):
            raise WalletError("Some keys don't belong to the %s network!" % NETWORKS[self.network]["name"])
        return w

    def add_wallet(self, w):
        self.wallets.append(w)
        wallet_ids = sorted(
            [
                int(f[0])
                for f in os.ilistdir(self.path)
                if f[0].isdigit() and f[1] == 0x4000
            ]
        )
        # get wallet id
        wid = (max(wallet_ids) + 1) if wallet_ids else 0
        newpath = self.path + ("/%d" % wid)
        platform.maybe_mkdir(newpath)
        w.save(self.keystore, path=newpath)

    def delete_wallet(self, w):
        if w not in self.wallets:
            raise WalletError("Wallet not found")
        self.wallets.pop(self.wallets.index(w))
        w.wipe()

    def find_wallet_from_address(self, addr: str, paths=None, index=None):
        if index is not None:
            for w in self.wallets:
                a, _ = w.get_address(index, self.network)
                print(a)
                if a == addr:
                    return w, (0, index)
        if paths is not None:
            # we can detect the wallet from just one path
            p = paths[0]
            if not p.startswith("m"):
                fingerprint = unhexlify(p[:8])
                derivation = bip32.parse_path("m"+p[8:])
            else:
                fingerprint = self.keystore.fingerprint
                derivation = bip32.parse_path(p)
            derivation_path = DerivationPath(fingerprint, derivation)
            for w in self.wallets:
                der = w.descriptor.check_derivation(derivation_path)
                if der is not None:
                    idx, branch_idx = der
                    a, _ = w.get_address(idx, self.network, branch_idx)
                    if a == addr:
                        return w, (idx, branch_idx)
        raise WalletError("Can't find wallet owning address %s" % addr)

    def preprocess_psbt(self, stream, fout):
        """
        Processes incoming PSBT, fills missing information and writes to fout.
        Returns:
        - wallets in inputs: dict {wallet: amount}
        - metadata for tx display including warnings that require user confirmation
        - default sighash to use for signing
        """
        # compress = True flag will make sure large fields won't be loaded to RAM
        psbtv = self.PSBTViewClass.view(stream, compress=True)

        # Default sighash to use for signing
        default_sighash = SIGHASH.ALL

        # Write global scope first
        psbtv.stream.seek(psbtv.offset)
        res = read_write(psbtv.stream, fout, psbtv.first_scope-psbtv.offset)

        # string representation of the Bitcoin for wallet processing
        fee = 0

        # here we will store all wallets that we detect in inputs
        # {wallet: amount}
        wallets = {}
        meta = {
            "inputs": [{} for i in range(psbtv.num_inputs)],
            "outputs": [{} for i in range(psbtv.num_outputs)],
        }

        fingerprint = self.keystore.fingerprint
        # We need to detect wallets owning inputs and outputs,
        # in case of liquid - unblind them.
        # Fill all necessary information:
        # For Bitcoin: bip32 derivations, witness script, redeem script
        # For Liquid: same + values, assets, commitments, proofs etc.
        # At the end we should have the most complete PSBT / PSET possible
        for i in range(psbtv.num_inputs):
            self.show_loader(title="Parsing input %d..." % i)
            # load input to memory, verify it (check prevtx hash)
            inp = psbtv.input(i)
            metainp = meta["inputs"][i]
            # verify, do not require non_witness_utxo if witness_utxo is set
            inp.verify(ignore_missing=True)

            # check sighash in the input
            if inp.sighash_type is not None and inp.sighash_type != default_sighash:
                if inp.sighash_type not in SIGHASH_NAMES:
                    raise WalletError("Unknown sighash type in the transaction!")
                metainp["sighash"] = SIGHASH_NAMES[inp.sighash_type]

            # Find wallets owning the inputs and fill scope data:
            # first we check already detected wallet owns the input
            # as in most common case all inputs are owned by the same wallet.
            wallet = None
            for w in wallets:
                # pass rangeproof offset if it's in the scope
                if w.fill_scope(inp, fingerprint):
                    wallet = w
                    break
            if wallet is None:
                # find wallet and append it to wallets
                for w in self.wallets:
                    # pass rangeproof offset if it's in the scope
                    if w.fill_scope(inp, fingerprint):
                        wallet = w
                        break
            # add wallet to tx wallets dict
            if wallet not in wallets:
                wallets[wallet] = 0

            value = inp.utxo.value
            fee += value

            wallets[wallet] = wallets.get(wallet, 0) + value
            metainp.update({
                "label": wallet.name if wallet else "Unknown wallet",
                "value": value,
            })
            # write non_witness_utxo separately if it exists (as we use compressed psbtview)
            non_witness_utxo_off = None
            off = psbtv.seek_to_scope(i)
            non_witness_utxo_off = psbtv.seek_to_value(b'\x00', from_current=True)
            if non_witness_utxo_off:
                non_witness_utxo_off += off
                l = compact.read_from(psbtv.stream)
                fout.write(b"\x01\x00")
                fout.write(compact.to_bytes(l))
                read_write(psbtv.stream, fout, l)
            inp.write_to(fout)

        # parse all outputs
        for i in range(psbtv.num_outputs):
            self.show_loader(title="Parsing output %d..." % i)
            out = psbtv.output(i)
            metaout = meta["outputs"][i]
            wallet = None
            for w in wallets:
                if w is None:
                    continue
                # pass rangeproof offset if it's in the scope
                if w.fill_scope(out, fingerprint):
                    wallet = w
                    break
            if wallet is None:
                # find wallet and append it to wallets
                for w in self.wallets:
                    if w.fill_scope(out, fingerprint):
                        wallet = w
                        break
            # Get values and store in metadata and wallets dict
            value = out.value
            fee -= value
            metaout.update({
                "label": wallet.name if wallet else "",
                "change": wallet is not None,
                "value": value,
                "address": self.get_address(out),
            })
            out.write_to(fout)

        meta["fee"] = fee
        return wallets, meta, default_sighash

    def sign_psbtview(self, psbtv, out_stream, wallets, sighash):
        for w in wallets:
            if w is None:
                continue
            # fill derivation paths from proprietary fields
            w.update_gaps(psbtv=psbtv)
            w.save(self.keystore)
        sig_count = 0
        with open(self.tempdir+"/sigs", "wb") as sig_stream:
            for i in range(psbtv.num_inputs):
                self.show_loader(title="Signing input %d of %d" % (i+1, psbtv.num_inputs))
                inp = psbtv.input(i)
                for w in wallets:
                    if w is None:
                        continue
                    w.fill_scope(inp, self.keystore.fingerprint)
                    # sign with wallet if it has private keys
                    if w.has_private_keys:
                        sig_count += w.sign_input(psbtv, i, sig_stream, sighash, inp)
                # sign with keystore
                sig_count += self.keystore.sign_input(psbtv, i, sig_stream, sighash, inp)
                # add separator
                sig_stream.write(b"\x00")
        if sig_count == 0:
            raise WalletError("We didn't add any signatures!\n\nMaybe you forgot to import the wallet?\n\nScan the wallet descriptor to import it.")
        # remove unnecessary stuff:
        with open(self.tempdir+"/sigs", "rb") as sig_stream:
            psbtv.write_to(out_stream, compress=True, extra_input_streams=[sig_stream])

    def wipe(self):
        """Deletes all wallets info"""
        self.wallets = []
        self.path = None
        platform.delete_recursively(self.root_path)
