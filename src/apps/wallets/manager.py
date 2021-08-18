from app import BaseApp
from gui.screens import Menu, InputScreen, Prompt, TransactionScreen
from .screens import WalletScreen, ConfirmWalletScreen
from gui.common import format_addr

import platform
import os
from binascii import hexlify, unhexlify, a2b_base64, b2a_base64
from bitcoin import script, bip32, ec, hashes
from bitcoin.psbt import DerivationPath
from bitcoin.psbtview import PSBTView
from bitcoin.liquid.psetview import PSETView, read_write
from bitcoin.liquid.networks import NETWORKS
from bitcoin.liquid.transaction import LSIGHASH as SIGHASH
from bitcoin.liquid.addresses import address as liquid_address
from .wallet import WalletError, Wallet
from .commands import DELETE, EDIT
from io import BytesIO
from bcur import bcur_encode, bcur_decode, bcur_decode_stream, bcur_encode_stream
from helpers import a2b_base64_stream, b2a_base64_stream, is_liquid
import gc
import json
import secp256k1

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
# asset management
ADD_ASSET = 0x07
DUMP_ASSETS = 0x08

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
# add sighash | rangeproof
for sh in list(SIGHASH_NAMES):
    SIGHASH_NAMES[sh | SIGHASH.RANGEPROOF] = SIGHASH_NAMES[sh] + " | RANGEPROOF"

def get_address(psbtout, network):
    """Helper function to get an address for every output"""
    if isinstance(network, str):
        network = NETWORKS[network]
    if is_liquid(network):
        # liquid fee
        if psbtout.script_pubkey.data == b"":
            return "Fee"
        if psbtout.blinding_pubkey is not None:
            # TODO: check rangeproof if it's present,
            # otherwise generate it ourselves if sighash is | RANGEPROOF
            bpub = ec.PublicKey.parse(psbtout.blinding_pubkey)
            return liquid_address(psbtout.script_pubkey, bpub, network)
    # finally just return bitcoin address or unconfidential
    try:
        return psbtout.script_pubkey.address(network)
    except Exception as e:
        # use hex if script doesn't have address representation
        return hexlify(psbtout.script_pubkey.data).decode()

class WalletManager(BaseApp):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    button = "Wallets"
    prefixes = [b"addwallet", b"sign", b"showaddr", b"listwallets", b"addasset", b"dumpassets"]
    name = "wallets"

    def __init__(self, path):
        self.root_path = path
        platform.maybe_mkdir(path)
        self.path = None
        self.wallets = []
        self.assets = {}

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
        self.load_assets()

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
            elif is_liquid(self.network) and prefix == b"addasset":
                return ADD_ASSET, stream
            elif is_liquid(self.network) and prefix == b"dumpassets":
                return DUMP_ASSETS, stream
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
        if data[:5] in [PSBTView.MAGIC, PSETView.MAGIC]:
            stream.seek(0)
            return SIGN_PSBT, stream
        if data[:4] in [b"cHNi", b"cHNl"]:
            try:
                psbt = a2b_base64(data)
                if psbt[:5] not in [PSBTView.MAGIC, PSETView.MAGIC]:
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
            if stream.read(5) in [PSBTView.MAGIC, PSETView.MAGIC]:
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
        elif cmd == ADD_ASSET:
            arr = stream.read().decode().split(" ")
            if len(arr) != 2:
                raise WalletError("Invalid number of arguments. Usage: addasset <hex_asset> asset_lbl")
            hexasset, assetlbl = arr
            if await show_screen(Prompt("Import asset?",
                    "Asset:\n\n"+format_addr(hexasset, letters=8, words=2)+"\n\nLabel: "+assetlbl)):
                asset = bytes(reversed(unhexlify(hexasset)))
                self.assets[asset] = assetlbl
                self.save_assets()
            return BytesIO(b"success"), {}
        elif cmd == DUMP_ASSETS:
            return BytesIO(self.assets_json()), {}
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
            PSBTViewClass, wallets, meta, sighash = self.preprocess_psbt(stream, fout)
        # now we can work with copletely filled psbt:
        with open(self.tempdir + "/filled_psbt", "rb") as f:
            psbtv = PSBTViewClass(f)

            # check if there are any custom sighashes
            custom_sighashes = meta['custom_sighashes']
            # ask the user if he wants to sign in case of non-default sighashes
            if len(custom_sighashes) > 0:
                txt = [("Input %d: " % i) + SIGHASH_NAMES[sh]
                        for (i, sh) in custom_sighashes]
                canceltxt = ("Only proceed %s" % SIGHASH_NAMES[sighash]) if len(custom_sighashes) != psbtv.num_inputs else "Cancel"
                confirm = await show_screen(Prompt("Warning!",
                    "\nCustom SIGHASH flags are used!\n\n"+"\n".join(txt),
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

            # liquid stuff - offer to label unknown assets
            if is_liquid(self.network) and len(meta.get("unknown_assets",[])) > 0:
                scr = Prompt(
                    "Warning!",
                    "\nUnknown assets in the transaction!\n\n\n"
                    "Do you want to label them?\n"
                    "Otherwise they will be rendered with partial hex id.",
                )
                if await show_screen(scr):
                    for asset in meta["unknown_assets"]:
                        # return False if the user cancelled
                        scr = InputScreen("Asset\n\n"+format_addr(hexlify(bytes(reversed(asset))).decode(), letters=8, words=2),
                                    note="\nChoose a label for unknown asset.\nBetter to keep it short, like LBTC or LDIY")
                        scr.ta.set_pos(190, 350)
                        scr.ta.set_width(100)
                        lbl = await show_screen(scr)
                        # if user didn't label the asset - go to the next one
                        if not lbl:
                            continue
                        else:
                            self.assets[asset] = lbl
                    self.save_assets()
                # replace labels we just saved
                for sc in meta["inputs"] + meta["outputs"]:
                    if sc.get("raw_asset"):
                        sc["asset"] = self.asset_label(sc["raw_asset"])

            # check if any inputs belong to unknown wallets
            # items in wallets list are tuples: (wallet, amount)
            if None in [wallet for wallet, amount in wallets]:
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
            for w, amount in wallets:
                if w is None:
                    name = "Unknown wallet"
                else:
                    name = w.name
                spends.append('%.8f BTC\nfrom "%s"' % (amount / 1e8, name))
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
        # add blinding key to the descriptor if we are on liquid network
        if is_liquid(self.network):
            desc = "blinded(slip77(%s),%s)" % (self.keystore.slip77_key, desc)
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
        - PSBTView class to use (PSBTView or PSETView)
        - wallets in inputs: list of tuples (wallet, amount)
        - metadata for tx display including warnings that require user confirmation
        - default sighash to use for signing
        """
        # TODO:
        # - separate btc vs liquid as much as possible
        # - make functions working with each input and output
        PSBTViewClass = PSETView if is_liquid(self.network) else PSBTView
        # compress = True flag will make sure large fields won't be loaded to RAM
        psbtv = PSBTViewClass.view(stream, compress=True)

        # Default sighash to use for signing
        default_sighash = SIGHASH.ALL
        # On Liquid we also cover rangeproofs
        if is_liquid(self.network):
            default_sighash |= SIGHASH.RANGEPROOF

        # Start with global fields of PSBT

        # On Liquid we check if txseed is provided (for deterministic blinding)
        # It will be None if it is not there.
        blinding_seed = psbtv.get_value(b"\xfc\x07specter\x00")
        if blinding_seed:
            hseed = hashes.tagged_hash_init("liquid/txseed", blinding_seed)
            vals = [] # values
            abfs = [] # asset blinding factors
            vbfs = [] # value blinding factors

        # Write global scope first
        psbtv.stream.seek(psbtv.offset)
        res = read_write(psbtv.stream, fout, psbtv.first_scope-psbtv.offset)

        # string representation of the Bitcoin for wallet processing
        if is_liquid(self.network):
            default_asset = "LBTC" if self.network == "liquidv1" else "tLBTC"
        else:
            default_asset = "BTC" if self.network == "main" else "tBTC"
        fee = { default_asset: 0 }

        # here we will store all wallets that we detect in inputs
        # wallet: {asset: amount}
        # For BTC it will be always { default_asset: amount }
        wallets = {}
        meta = {
            "inputs": [{} for i in range(psbtv.num_inputs)],
            "outputs": [{} for i in range(psbtv.num_outputs)],
            "default_asset": default_asset,
        }

        fingerprint = self.keystore.fingerprint
        # We need to detect wallets owning inputs and outputs,
        # in case of liquid - unblind them.
        # Fill all necessary information:
        # For Bitcoin: bip32 derivations, witness script, redeem script
        # For Liquid: same + values, assets, commitments, proofs etc.
        # At the end we should have the most complete PSBT / PSET possible
        for i in range(psbtv.num_inputs):
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

            # in Liquid we may need to rewind the rangeproof to get values
            rangeproof_offset = None
            if is_liquid(self.network):
                off = psbtv.seek_to_scope(i)
                # find offset of the rangeproof if it exists
                rangeproof_offset = psbtv.seek_to_value(b'\xfc\x04pset\x0e', from_current=True)
                # add scope offset
                if rangeproof_offset is not None:
                    rangeproof_offset += off

            # Find wallets owning the inputs and fill scope data:
            # first we check already detected wallet owns the input
            # as in most common case all inputs are owned by the same wallet.
            wallet = None
            for w in wallets:
                # pass rangeproof offset if it's in the scope
                if w.fill_scope(inp, fingerprint,
                                stream=psbtv.stream, rangeproof_offset=rangeproof_offset):
                    wallet = w
                    break
            if wallet is None:
                # find wallet and append it to wallets
                for w in self.wallets:
                    # pass rangeproof offset if it's in the scope
                    if w.fill_scope(inp, fingerprint,
                                    stream=psbtv.stream, rangeproof_offset=rangeproof_offset):
                        wallet = w
                        break
            # add wallet to tx wallets dict
            if wallet not in wallets:
                wallets[wallet] = {}

            # Get values (and assets) and store in metadata and wallets dict
            if not is_liquid(self.network):
                # bitcoin it easy, just add value to the asset
                asset = default_asset
                value = inp.utxo.value
            else:
                # we don't know yet if we unblinded stuff or not
                asset = inp.asset or inp.utxo.asset
                value = inp.value or inp.utxo.value
                # blinded assets are 33-bytes long, unblinded - 32
                if not (len(asset) == 32 and isinstance(value, int)):
                    asset = None
                    value = 0
                if blinding_seed:
                    # update blinding seed
                    hseed.update(bytes(reversed(inp.txid)))
                    hseed.update(inp.vout.to_bytes(4,'little'))
                    vals.append(value)
                    abfs.append(inp.asset_blinding_factor or b"\x00"*32)
                    vbfs.append(inp.value_blinding_factor or b"\x00"*32)

            wallets[wallet][asset] = wallets[wallet].get(asset, 0) + value
            metainp.update({
                "label": wallet.name if wallet else "Unknown wallet",
                "value": value,
            })
            if asset != default_asset:
                metainp.update({"asset": self.asset_label(asset)})
                if asset not in self.assets:
                    metainp.update({"raw_asset": asset})
            inp.write_to(fout)

        # if blinding seed is set - blind outputs that are missing proofs
        if is_liquid(self.network) and blinding_seed:
            blinding_out_indexes = []
            for i in range(psbtv.num_outputs):
                out = psbtv.output(i)
                hseed.update(out.script_pubkey.serialize())
            txseed = hseed.digest()
            for i in range(psbtv.num_outputs):
                out = psbtv.output(i)
                if out.blinding_pubkey:
                    blinding_out_indexes.append(i)
                    abfs.append(hashes.tagged_hash("liquid/abf", txseed+i.to_bytes(4,'little')))
                    vbfs.append(hashes.tagged_hash("liquid/vbf", txseed+i.to_bytes(4,'little')))
                    vals.append(out.value)
            # get last vbf from scope
            out = psbtv.output(blinding_out_indexes[-1])
            if out.value_blinding_factor:
                vbfs[-1] = out.value_blinding_factor
            else:
                raise NotImplementedError()
                vbfs[-1] = secp256k1.pedersen_blind_generator_blind_sum(vals, abfs, vbfs, psbtv.num_inputs)

            # calculate commitments (surj proof etc)

            # in_tags = [inp.asset for inp in self.inputs]
            # in_gens = [secp256k1.generator_parse(inp.utxo.asset) for inp in self.inputs]

            # for i, out in enumerate(self.outputs):
            #     if out.blinding_pubkey is None:
            #         continue
            #     gen = secp256k1.generator_generate_blinded(out.asset, out.asset_blinding_factor)
            #     out.asset_commitment = secp256k1.generator_serialize(gen)
            #     value_commitment = secp256k1.pedersen_commit(out.value_blinding_factor, out.value, gen)
            #     out.value_commitment = secp256k1.pedersen_commitment_serialize(value_commitment)

            #     proof_seed = hashes.tagged_hash("liquid/surjection_proof", txseed+i.to_bytes(4,'little'))
            #     proof, in_idx = secp256k1.surjectionproof_initialize(in_tags, out.asset, seed=proof_seed)
            #     secp256k1.surjectionproof_generate(proof, in_idx, in_gens, gen, self.inputs[in_idx].asset_blinding_factor, out.asset_blinding_factor)
            #     out.surjection_proof = secp256k1.surjectionproof_serialize(proof)

            #     # generate range proof
            #     rangeproof_nonce = hashes.tagged_hash("liquid/range_proof", txseed+i.to_bytes(4,'little'))
            #     out.reblind(rangeproof_nonce)
        # otherwise - verify all outputs
        for i in range(psbtv.num_outputs):
            out = psbtv.output(i)
            metaout = meta["outputs"][i]
            rangeproof_offset = None
            # surj_proof_offset = None
            # find rangeproof and surjection proof
            if is_liquid(self.network):
                off = psbtv.seek_to_scope(psbtv.num_inputs+i)
                # find offset of the rangeproof if it exists
                rangeproof_offset = psbtv.seek_to_value(b'\xfc\x04pset\x04', from_current=True)
                if rangeproof_offset is None:
                    psbtv.seek_to_scope(psbtv.num_inputs+i)
                    # alternative key definition (psetv0)
                    rangeproof_offset = psbtv.seek_to_value(b'\xfc\x08elements\x04', from_current=True)
                if rangeproof_offset is not None:
                    rangeproof_offset += off
                # psbtv.seek_to_scope(psbtv.num_inputs+i)
                # surj_proof_offset = psbtv.seek_to_value(b'\xfc\x04pset\x05', from_current=True)
                # if surj_proof_offset is None:
                #     psbtv.seek_to_scope(psbtv.num_inputs+i)
                #     # alternative key definition (psetv0)
                #     surj_proof_offset = psbtv.seek_to_value(b'\xfc\x08elements\x04', from_current=True)
                # if surj_proof_offset is not None:
                #     surj_proof_offset += off
            wallet = None
            for w in wallets:
                # pass rangeproof offset if it's in the scope
                if w.fill_scope(out, fingerprint,
                                stream=psbtv.stream,
                                rangeproof_offset=rangeproof_offset,
                                # surj_proof_offset=surj_proof_offset,
                ):
                    wallet = w
                    break
            if wallet is None:
                # find wallet and append it to wallets
                for w in self.wallets:
                    # pass rangeproof offset if it's in the scope
                    if w.fill_scope(out, fingerprint,
                                    stream=psbtv.stream,
                                    rangeproof_offset=rangeproof_offset,
                                    # surj_proof_offset=surj_proof_offset,
                    ):
                        wallet = w
                        break
            # - lq: generate commitments and rangeproofs
            #       if blinding pubkey is set and seed is set.
            # Get values (and assets) and store in metadata and wallets dict
            if not is_liquid(self.network):
                # bitcoin it easy, just add value to the asset
                asset = default_asset
                value = out.value
            else:
                # we don't know yet if we unblinded stuff or not
                asset = out.asset or out.asset_commitment
                value = out.value or out.value_commitment
                # blinded assets are 33-bytes long, unblinded - 32
                if not (len(asset) == 32 and isinstance(value, int)):
                    asset = None
                    value = 0
            metaout.update({
                "label": wallet.name if wallet else "",
                "change": wallet is not None,
                "value": value,
                "address": get_address(out, self.network),
            })
            if asset != default_asset:
                metaout.update({"asset": self.asset_label(asset)})
                if asset not in self.assets:
                    metaout.update({"raw_asset": asset})
            out.write_to(fout, skip_separator=True)
            # write rangeproofs and surjection proofs
            # separator
            fout.write(b"\x00")

        return PSBTViewClass, wallets, meta, default_sighash

    def sign_psbtview(self, psbtv, out_stream, wallets, sighash):
        for w, _ in wallets:
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
                for w, _ in wallets:
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

    def parse_psbtview(self, psbtv):
        """Detects a wallet for transaction and returns an object to display"""
        # wallets owning the inputs
        # will be a tuple (wallet, amount)
        # if wallet is not found - (None, amount)
        wallets = []
        amounts = []

        # calculate fee
        if is_liquid(self.network):
            fee = 0
            default_asset = "LBTC" if self.network == "liquidv1" else "tLBTC"
        else:
            fee = sum([psbtv.input(i).utxo.value for i in range(psbtv.num_inputs)])
            fee -= sum([psbtv.output(i).value for i in range(psbtv.num_outputs)])
            default_asset = "BTC" if self.network == "main" else "tBTC"

        net = NETWORKS[self.network]

        # metadata for GUI
        meta = {
            # we can't display fee percent if there are many assets
            "hide_fee_percent": is_liquid(self.network),
            "default_asset": default_asset,
            "inputs": [{} for i in range(psbtv.num_inputs)],
            "outputs": [{} for i in range(psbtv.num_outputs)],
            "warnings": [],
            "unknown_assets": [],
        }
        for i in range(psbtv.num_outputs):
            out = psbtv.output(i)
            if is_liquid(self.network) and out.script_pubkey.data == b"":
                fee += out.value
            meta["outputs"][i].update({
                "address": get_address(out, net),
                "value": out.value,
                "change": False,
            })
            if is_liquid(self.network):
                meta["outputs"][i]["asset"] = self.asset_label(out.asset)
                if out.asset not in self.assets:
                    meta["outputs"][i]["raw_asset"] = out.asset
                    if out.asset not in meta["unknown_assets"]:
                        meta["unknown_assets"].append(out.asset)

        meta["fee"] = fee
        # detect wallet for all inputs
        for i in range(psbtv.num_inputs):
            self.show_loader(title="Detecting wallet for input %d of %d..." % (i+1, psbtv.num_inputs))
            inp = psbtv.input(i)
            found = False
            # value is stored in utxo for btc tx and in unblinded tx vin for liquid
            value = inp.utxo.value if not is_liquid(self.network) else inp.value

            if is_liquid(self.network):
                meta["inputs"][i]["asset"] = self.asset_label(inp.asset)
                if inp.asset not in self.assets:
                    meta["inputs"][i]["raw_asset"] = inp.asset
                    if inp.asset not in meta["unknown_assets"]:
                        meta["unknown_assets"].append(inp.asset)

            meta["inputs"][i].update({
                "label": "Unknown wallet",
                "value": value,
                "sighash": SIGHASH_NAMES[inp.sighash_type or SIGHASH.ALL]
            })
            for w in self.wallets:
                if w.owns(inp):
                    idx, branch_idx = w.get_derivation(inp.bip32_derivations)
                    meta["inputs"][i]["label"] = w.name
                    if branch_idx == 1:
                        meta["inputs"][i]["label"] += " change %d" % idx
                    elif branch_idx == 0:
                        meta["inputs"][i]["label"] += " #%d" % idx
                    else:
                        meta["inputs"][i]["label"] += " #%d on branch %d" % (idx, branch_idx)
                    if w not in wallets:
                        wallets.append(w)
                        amounts.append(value)
                    else:
                        idx = wallets.index(w)
                        amounts[idx] += value
                    found = True
                    break
            if not found:
                if None not in wallets:
                    wallets.append(None)
                    amounts.append(value)
                else:
                    idx = wallets.index(None)
                    amounts[idx] += value

        if None in wallets:
            meta["warnings"].append("Unknown wallet in input!")
        if len(wallets) > 1:
            meta["warnings"].append("Mixed inputs!")

        # check change outputs
        for i in range(psbtv.num_outputs):
            self.show_loader(title="Detecting wallet for output %d of %d..." % (i+1, psbtv.num_outputs))
            out = psbtv.output(i)
            for w in wallets:
                if w is None:
                    continue
                if w.owns(out):
                    meta["outputs"][i]["change"] = True
                    meta["outputs"][i]["label"] = w.name
                    break
        # check gap limits
        gaps = [[] + w.gaps if w is not None else [0, 0] for w in wallets]
        # update gaps according to all inputs
        # because if input and output use the same branch (recv / change)
        # it's ok if both are larger than gap limit
        # but differ by less than gap limit
        # (i.e. old wallet is used)
        for inidx in range(psbtv.num_inputs):
            inp = psbtv.input(inidx)
            for i, w in enumerate(wallets):
                if w is None:
                    continue
                if w.owns(inp):
                    idx, branch_idx = w.get_derivation(inp.bip32_derivations)
                    if gaps[i][branch_idx] < idx + type(w).GAP_LIMIT:
                        gaps[i][branch_idx] = idx + type(w).GAP_LIMIT
        # check all outputs if index is ok
        for i in range(psbtv.num_outputs):
            out = psbtv.output(i)
            if not meta["outputs"][i]["change"]:
                continue
            for j, w in enumerate(wallets):
                if w.owns(out):
                    idx, branch_idx = w.get_derivation(out.bip32_derivations)
                    if branch_idx == 1:
                        meta["outputs"][i]["label"] += " change %d" % idx
                    elif branch_idx == 0:
                        meta["outputs"][i]["label"] += " #%d" % idx
                    else:
                        meta["outputs"][i]["label"] += " #%d on branch %d" % (idx, branch_idx)
                    # add warning if idx beyond gap
                    if idx > gaps[j][branch_idx]:
                        meta["warnings"].append(
                            "Address index %d is beyond the gap limit!" % idx
                        )
                        # one warning of this type is enough
                        break
        wallets = [(wallets[i], amounts[i]) for i in range(len(wallets))]
        return wallets, meta

    def wipe(self):
        """Deletes all wallets info"""
        self.wallets = []
        self.path = None
        platform.delete_recursively(self.root_path)

    ##### liquid stuff ######

    def asset_label(self, asset):
        if asset is None:
            return "Undefined"
        # passing "BTC" shouldn't break things
        if isinstance(asset, str):
            return asset
        if asset in self.assets:
            return self.assets[asset]
        h = hexlify(bytes(reversed(asset))).decode()
        # hex repr of the asset
        return "L-"+h[:4]+"..."+h[-4:]

    def assets_json(self):
        assets = {}
        # no support for bytes...
        for asset in self.assets:
            assets[hexlify(bytes(reversed(asset))).decode()] = self.assets[asset]
        return json.dumps(assets)

    @property
    def assets_path(self):
        return self.root_path + "/uid" + self.keystore.uid

    @property
    def assets_file(self):
        return self.assets_path + "/assets_" + self.network

    def save_assets(self):
        platform.maybe_mkdir(self.assets_path)
        assets = self.assets_json()
        self.keystore.save_aead(self.assets_file, plaintext=assets.encode(), key=self.keystore.userkey)


    def load_assets(self):
        self.assets = {}
        # known Liquid assets
        if self.network == "liquidv1":
            self.assets.update({
                bytes(reversed(unhexlify("6f0279e9ed041c3d710a9f57d0c02928416460c4b722ae3457a11eec381c526d"))): "LBTC",
                bytes(reversed(unhexlify("ce091c998b83c78bb71a632313ba3760f1763d9cfcffae02258ffa9865a37bd2"))): "USDt",
            })
        platform.maybe_mkdir(self.assets_path)
        if platform.file_exists(self.assets_file):
            _, assets = self.keystore.load_aead(self.assets_file, key=self.keystore.userkey)
            assets = json.loads(assets.decode())
            # no support for bytes...
            for asset in assets:
                self.assets[bytes(reversed(unhexlify(asset)))] = assets[asset]
