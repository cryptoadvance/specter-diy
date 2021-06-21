from app import BaseApp
from gui.screens import Menu, InputScreen, Prompt, TransactionScreen
from .screens import WalletScreen, ConfirmWalletScreen

import platform
import os
from binascii import hexlify, unhexlify, a2b_base64, b2a_base64
from bitcoin.psbt import PSBT, DerivationPath
from bitcoin.networks import NETWORKS
from bitcoin import script, bip32
from bitcoin.transaction import SIGHASH
from .wallet import WalletError, Wallet
from .commands import DELETE, EDIT
from io import BytesIO
from bcur import bcur_encode, bcur_decode, bcur_decode_stream, bcur_encode_stream
from helpers import a2b_base64_stream
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
    (SIGHASH.ALL | SIGHASH.ANYONECANPAY): "ALL | ANYONECANPAY",
    (SIGHASH.NONE | SIGHASH.ANYONECANPAY): "NONE | ANYONECANPAY",
    (SIGHASH.SINGLE | SIGHASH.ANYONECANPAY): "SINGLE | ANYONECANPAY",
}

class WalletManager(BaseApp):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    button = "Wallets"
    WALLETS = [Wallet]
    prefixes = [b"addwallet", b"sign", b"showaddr", b"listwallets"]
    name = "wallets"

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

    @classmethod
    def register(cls, walletcls):
        """Registers an additional wallet class"""
        # check if it's already there
        if walletcls in cls.WALLETS:
            return
        cls.WALLETS.append(walletcls)

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
        if data[:4] == b"cHNi":
            try:
                psbt = a2b_base64(data)
                if psbt[:5] != b"psbt\xff":
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
            if stream.read(5) == b"psbt\xff":
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
            platform.delete_recursively(self.tempdir)
            if res is not None:
                data, hsh = bcur_encode(res.read(), upper=True)
                bcur_res = (b"UR:BYTES/" + hsh + "/" + data)
                obj = {
                    "title": "Transaction is signed!",
                    "message": "Scan it with your wallet",
                }
                gc.collect()
                return BytesIO(bcur_res), obj
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
                psbt = PSBT.read_from(f, compress=True)
            # cleanup
            platform.delete_recursively(self.tempdir)
        else:
            psbt = PSBT.read_from(stream, compress=True)
        # check if all utxos are there and if there are custom sighashes
        sighash = SIGHASH.ALL
        custom_sighashes = []
        for i, inp in enumerate(psbt.inputs):
            if (not inp.is_verified) and inp.witness_utxo is None and inp.non_witness_utxo is None:
                raise WalletError("Invalid PSBT - missing previous transaction")
            if inp.sighash_type and inp.sighash_type != SIGHASH.ALL:
                custom_sighashes.append((i, inp.sighash_type))

        if len(custom_sighashes) > 0:
            txt = [("Input %d: " % i) + SIGHASH_NAMES[sh]
                    for (i, sh) in custom_sighashes]
            canceltxt = "Only sign ALL" if len(custom_sighashes) != len(psbt.inputs) else "Cancel"
            confirm = await show_screen(Prompt("Warning!",
                "\nCustom SIGHASH flags are used!\n\n"+"\n".join(txt),
                confirm_text="Sign anyway", cancel_text=canceltxt
            ))
            if confirm:
                sighash = None
            else:
                if len(custom_sighashes) == len(psbt.inputs):
                    # nothing to sign
                    return
        wallets, meta = self.parse_psbt(psbt=psbt)
        # there is an unknown wallet
        # wallet is a list of tuples: (wallet, amount)
        if None in [w[0] for w in wallets]:
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
        spends = []
        for w, amount in wallets:
            if w is None:
                name = "Unknown wallet"
            else:
                name = w.name
            spends.append('%.8f BTC\nfrom "%s"' % (amount / 1e8, name))
        title = "Spending:\n" + "\n".join(spends)
        res = await show_screen(TransactionScreen(title, meta))
        if res:
            self.show_loader(title="Signing transaction...")
            sigsStart = 0
            for i, inp in enumerate(psbt.inputs):
                sigsStart += len(list(inp.partial_sigs.keys()))
            for w, _ in wallets:
                if w is None:
                    continue
                # fill derivation paths from proprietary fields
                w.update_gaps(psbt=psbt)
                w.save(self.keystore)
                w.fill_psbt(psbt, self.keystore.fingerprint)
                if w.has_private_keys:
                    w.sign_psbt(psbt, sighash)
            self.keystore.sign_psbt(psbt, sighash)
            # remove unnecessary stuff:
            out_psbt = PSBT(psbt.tx)
            sigsEnd = 0
            for i, inp in enumerate(psbt.inputs):
                sigsEnd += len(list(inp.partial_sigs.keys()))
                out_psbt.inputs[i].partial_sigs = inp.partial_sigs
            del psbt
            gc.collect()
            if sigsEnd == sigsStart:
                raise WalletError("We didn't add any signatures!\n\nMaybe you forgot to import the wallet?\n\nScan the wallet descriptor to import it.")
            if encoding == BASE64_STREAM:
                # TODO: also use ram file
                txt = b2a_base64(out_psbt.serialize()).decode().strip()
            else:
                txt = out_psbt.serialize()
            return BytesIO(txt)

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
        w = None
        # going through all wallet classes and trying to load
        # first we verify descriptor sig in the folder
        for walletcls in self.WALLETS:
            try:
                # pass path and key for verification
                w = walletcls.from_path(path, self.keystore)
                # if fails - we continue, otherwise - we are done
                break
            except Exception as e:
                pass
        # if we failed to load -> delete folder and throw an error
        if w is None:
            platform.delete_recursively(path, include_self=True)
            raise WalletError("Can't load wallet from %s" % path)
        return w

    def create_default_wallet(self, path):
        """Creates default p2wpkh wallet with name `Default`"""
        der = "m/84h/%dh/0h" % NETWORKS[self.network]["bip32"]
        xpub = self.keystore.get_xpub(der)
        desc = "Default&wpkh([%s%s]%s)" % (
            hexlify(self.keystore.fingerprint).decode(),
            der[1:],
            xpub.to_base58(NETWORKS[self.network]["xpub"]),
        )
        w = Wallet.parse(desc, path)
        # pass keystore to encrypt data
        w.save(self.keystore)
        platform.sync()
        return w

    def parse_wallet(self, desc):
        w = None
        # trying to find a correct wallet type
        errors = []
        for walletcls in self.WALLETS:
            try:
                w = walletcls.parse(desc)
                # if fails - we continue, otherwise - we are done
                break
            except Exception as e:
                # raise if only one wallet class is available (most cases)
                errors.append(e)
        if w is None:
            raise WalletError("Can't detect matching wallet type\n"+"\n".join([str(e) for e in errors]))
        if str(w.descriptor) in [str(ww.descriptor) for ww in self.wallets]:
            raise WalletError("Wallet with this descriptor already exists")
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

    def parse_psbt(self, psbt):
        """Detects a wallet for transaction and returns an object to display"""
        # wallets owning the inputs
        # will be a tuple (wallet, amount)
        # if wallet is not found - (None, amount)
        wallets = []
        amounts = []

        # calculate fee
        fee = sum([psbt.utxo(i).value for i in range(len(psbt.inputs))])
        fee -= sum([out.value for out in psbt.tx.vout])

        # metadata for GUI
        meta = {
            "inputs": [{} for i in psbt.tx.vin],
            "outputs": [
                {
                    "address": out.script_pubkey.address(NETWORKS[self.network]),
                    "value": out.value,
                    "change": False,
                }
                for out in psbt.tx.vout
            ],
            "fee": fee,
            "warnings": [],
        }
        # detect wallet for all inputs
        for i, inp in enumerate(psbt.inputs):
            found = False
            utxo = psbt.utxo(i)
            meta["inputs"][i] = {
                "label": "Unknown wallet",
                "value": utxo.value,
                "sighash": SIGHASH_NAMES[inp.sighash_type or SIGHASH.ALL]
            }
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
                        amounts.append(utxo.value)
                    else:
                        idx = wallets.index(w)
                        amounts[idx] += utxo.value
                    found = True
                    break
            if not found:
                if None not in wallets:
                    wallets.append(None)
                    amounts.append(psbt.utxo(i).value)
                else:
                    idx = wallets.index(None)
                    amounts[idx] += psbt.utxo(i).value

        if None in wallets:
            meta["warnings"].append("Unknown wallet in input!")
        if len(wallets) > 1:
            meta["warnings"].append("Mixed inputs!")

        # check change outputs
        for i, out in enumerate(psbt.outputs):
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
        for inidx, inp in enumerate(psbt.inputs):
            for i, w in enumerate(wallets):
                if w is None:
                    continue
                if w.owns(inp):
                    idx, branch_idx = w.get_derivation(inp.bip32_derivations)
                    if gaps[i][branch_idx] < idx + type(w).GAP_LIMIT:
                        gaps[i][branch_idx] = idx + type(w).GAP_LIMIT
        # check all outputs if index is ok
        for i, out in enumerate(psbt.outputs):
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
