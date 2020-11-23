from app import BaseApp
from gui.screens import Menu, InputScreen, Prompt, TransactionScreen
from .screens import WalletScreen, ConfirmWalletScreen

import platform
import os
from binascii import hexlify, unhexlify, a2b_base64, b2a_base64
from bitcoin.psbt import PSBT
from bitcoin.networks import NETWORKS
from bitcoin import script, bip32
from .wallet import WalletError, Wallet
from .commands import DELETE, EDIT
from io import BytesIO
from bcur import bcur_encode, bcur_decode

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


class WalletManager(BaseApp):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    button = "Wallets"
    WALLETS = [Wallet]

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
        buttons += [(w, w.name) for w in self.wallets]
        menuitem = await show_screen(Menu(buttons, last=(255, None)))
        if menuitem == 255:
            # we are done
            return False
        else:
            w = menuitem
            # pass wallet and network
            self.show_loader(title="Loading wallet...")
            scr = WalletScreen(w, self.network, idx=w.unused_recv)
            cmd = await show_screen(scr)
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
                    title="Enter new wallet name", note="", suggestion=w.name
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
        if data.startswith(b"bitcoin:") or b"index=" in data:
            if data.startswith(b"bitcoin:"):
                stream.seek(8)
            else:
                stream.seek(0)
            return VERIFY_ADDRESS, stream

        return None, None

    async def process_host_command(self, stream, show_screen):
        cmd, stream = self.parse_stream(stream)
        if cmd == SIGN_PSBT:
            res = await self.sign_psbt(stream, show_screen)
            if res is not None:
                obj = {
                    "title": "Transaction is signed!",
                    "message": "Scan it with your wallet",
                }
                return res, obj
            return
        if cmd == SIGN_BCUR:
            data = stream.read().split(b"/")[-1].decode()
            b64_psbt = b2a_base64(bcur_decode(data)).strip()
            res = await self.sign_psbt(BytesIO(b64_psbt), show_screen)
            if res is not None:
                data, hsh = bcur_encode(a2b_base64(res.read()))
                bcur_res = (
                    b"UR:BYTES/" + hsh.encode().upper() + "/" + data.encode().upper()
                )
                obj = {
                    "title": "Transaction is signed!",
                    "message": "Scan it with your wallet",
                }
                return BytesIO(bcur_res), obj
            return
        elif cmd == ADD_WALLET:
            # read content, it's small
            desc = stream.read().decode()
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
            w = self.find_wallet_from_address(addr, idx)
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
            paths = path.split(b",")
            if len(paths) == 0:
                raise WalletError("Invalid path argument")
            res = await self.showaddr(
                paths, script_type, redeem_script, show_screen=show_screen
            )
            return BytesIO(res), {}
        else:
            raise WalletError("Unknown command")

    async def sign_psbt(self, stream, show_screen):
        data = a2b_base64(stream.read())
        psbt = PSBT.parse(data)
        wallets, meta = self.parse_psbt(psbt=psbt)
        spends = []
        for w, amount in wallets:
            if w is None:
                name = "Unkown wallet"
            else:
                name = w.name
            spends.append('%.8f BTC\nfrom "%s"' % (amount / 1e8, name))
        title = "Spending:\n" + "\n".join(spends)
        res = await show_screen(TransactionScreen(title, meta))
        if res:
            self.show_loader(title="Signing transaction...")
            for w, _ in wallets:
                if w is None:
                    continue
                # fill derivation paths from proprietary fields
                w.update_gaps(psbt=psbt)
                w.save(self.keystore)
                psbt = w.fill_psbt(psbt, self.keystore.fingerprint)
            self.keystore.sign_psbt(psbt)
            # remove unnecessary stuff:
            out_psbt = PSBT(psbt.tx)
            for i, inp in enumerate(psbt.inputs):
                out_psbt.inputs[i].partial_sigs = inp.partial_sigs
            txt = b2a_base64(out_psbt.serialize()).decode().strip()
            return BytesIO(txt)

    async def confirm_new_wallet(self, w, show_screen):
        keys = [{"key": k, "mine": self.keystore.owns(k)} for k in w.get_keys()]
        if not any([k["mine"] for k in keys]):
            raise WalletError("None of the keys belong to the device")
        return await show_screen(ConfirmWalletScreen(w.name, w.policy, keys))

    async def showaddr(
        self, paths: list, script_type: str, redeem_script=None, show_screen=None
    ) -> str:
        if redeem_script is not None:
            redeem_script = script.Script(unhexlify(redeem_script))
        # first check if we have corresponding wallet:
        # - just take last 2 indexes of the derivation
        # and see if redeem script matches
        address = None
        if redeem_script is not None:
            if script_type == b"wsh":
                address = script.p2wsh(redeem_script).address(NETWORKS[self.network])
            elif script_type == b"sh-wsh":
                address = script.p2sh(script.p2wsh(redeem_script)).address(
                    NETWORKS[self.network]
                )
            else:
                raise HostError("Unsupported script type: %s" % script_type)
        # in our wallets every key
        # has the same two last indexes for derivation
        path = paths[0]
        if not path.startswith(b"m/"):
            path = b"m" + path[8:]
        derivation = bip32.parse_path(path.decode())

        # if not multisig:
        if address is None and len(paths) == 1:
            pub = self.keystore.get_xpub(derivation)
            if script_type == b"wpkh":
                address = script.p2wpkh(pub).address(NETWORKS[self.network])
            elif script_type == b"sh-wpkh":
                address = script.p2sh(
                    script.p2wpkh(pub)
                ).address(NETWORKS[self.network])
            else:
                raise WalletError("Unsupported script type: %s" % script_type)

        if len(derivation) >= 2:
            derivation = derivation[-2:]
        else:
            raise WalletError("Invalid derivation")
        if address is None:
            raise WalletError("Can't derive address. Provide redeem script.")
        try:
            change = bool(derivation[0])
            w = self.find_wallet_from_address(address, derivation[1], change=change)
        except Exception as e:
            raise WalletError("%s" % e)
        if show_screen is not None:
            await show_screen(
                WalletScreen(w, self.network, derivation[1], change=change)
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
        for walletcls in self.WALLETS:
            try:
                w = walletcls.parse(desc)
                # if fails - we continue, otherwise - we are done
                break
            except Exception as e:
                pass
        if w is None:
            raise WalletError("Can't detect matching wallet type")
        if w.descriptor() in [ww.descriptor() for ww in self.wallets]:
            raise WalletError("Wallet with this descriptor already exists")
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
        newpath = self.path + ("/%d" % (max(wallet_ids) + 1))
        platform.maybe_mkdir(newpath)
        w.save(self.keystore, path=newpath)

    def delete_wallet(self, w):
        if w not in self.wallets:
            raise WalletError("Wallet not found")
        self.wallets.pop(self.wallets.index(w))
        w.wipe()

    def find_wallet_from_address(self, addr: str, idx: int, change=False):
        for w in self.wallets:
            a, gap = w.get_address(idx, self.network, change)
            if a == addr:
                return w
        raise WalletError("Can't find wallet owning address %s" % addr)

    def parse_psbt(self, psbt):
        """Detects a wallet for transaction and returns an object to display"""
        # wallets owning the inputs
        # will be a tuple (wallet, amount)
        # if wallet is not found - (None, amount)
        wallets = []
        amounts = []

        # calculate fee
        fee = sum([inp.witness_utxo.value for inp in psbt.inputs])
        fee -= sum([out.value for out in psbt.tx.vout])

        # metadata for GUI
        meta = {
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
        for inp in psbt.inputs:
            found = False
            for w in self.wallets:
                if w.owns(inp):
                    if w not in wallets:
                        wallets.append(w)
                        amounts.append(inp.witness_utxo.value)
                    else:
                        idx = wallets.index(w)
                        amounts[idx] += inp.witness_utxo.value
                    found = True
                    break
            if not found:
                if None not in wallets:
                    wallets.append(None)
                    amounts.append(inp.witness_utxo.value)
                else:
                    idx = wallets.index(None)
                    amounts[idx] += inp.witness_utxo.value

        if None in wallets:
            meta["warnings"].append("Unknown wallet in input!")
        if len(wallets) > 1:
            warnings.append("Mixed inputs!")

        # check change outputs
        for i, out in enumerate(psbt.outputs):
            for w in wallets:
                if w is None:
                    continue
                if w.owns(psbt_out=out, tx_out=psbt.tx.vout[i]):
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
        for inp in psbt.inputs:
            for i, w in enumerate(wallets):
                if w is None:
                    continue
                if w.owns(inp):
                    change, idx = w.get_derivation(inp)
                    if gaps[i][change] < idx + type(w).GAP_LIMIT:
                        gaps[i][change] = idx + type(w).GAP_LIMIT
        # check all outputs if index is ok
        for i, out in enumerate(psbt.outputs):
            if not meta["outputs"][i]["change"]:
                continue
            for j, w in enumerate(wallets):
                if w.owns(psbt_out=out, tx_out=psbt.tx.vout[i]):
                    change, idx = w.get_derivation(out)
                    if change:
                        meta["outputs"][i]["label"] += " (change %d)" % idx
                    else:
                        meta["outputs"][i]["label"] += " (address %d)" % idx
                    # add warning if idx beyond gap
                    if idx > gaps[j][change]:
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
