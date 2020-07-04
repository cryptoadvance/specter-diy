import sys, gc, json
from binascii import hexlify, unhexlify
from io import BytesIO
import asyncio

from keystore import FlashKeyStore
from platform import CriticalErrorWipeImmediately, set_usb_mode, reboot
from hosts import HostError
from bitcoin import ec, psbt, bip32, bip39, script
from bitcoin.psbt import PSBT
from bitcoin.networks import NETWORKS
# small helper functions
from helpers import gen_mnemonic
from gui.commands import EDIT, DELETE
from errors import BaseError

class SpecterError(BaseError):
    NAME = "Specter error"

class Specter:
    """Specter class.
    Call .start() method to register in the event loop
    It will then call the .setup() and .main() functions to display the GUI
    """
    def __init__(self, gui, wallet_manager, keystore, hosts, settings_path):
        self.hosts = hosts
        self.keystore = keystore
        self.gui = gui
        self.wallet_manager = wallet_manager
        self.path = settings_path
        self.load_network(self.path)
        self.current_menu = self.initmenu
        self.just_booted = True
        self.usb = False
        self.dev = False

    def start(self):
        # start the GUI
        self.gui.start()
        # register coroutines for all hosts
        for host in self.hosts:
            host.start(self)
        asyncio.run(self.setup())

    async def handle_exception(self, exception, next_fn):
        """
        Handle exception, show proper error message
        and return next function to call and await
        """
        try:
            raise exception
        except CriticalErrorWipeImmediately as e:
            # wipe all wallets
            self.wallet_manager.wipe()
            # show error
            await self.gui.error("%s" % e)
            # TODO: actual reboot here
            return self.setup
        # catch an expected error
        except BaseError as e:
            # show error
            await self.gui.alert(e.NAME, "%s" % e)
            # restart
            return next_fn
        # show trace for unexpected errors
        except Exception as e:
            print(e)
            b = BytesIO()
            sys.print_exception(e, b)
            await self.gui.error("Something unexpected happened...\n\n%s" % b.getvalue().decode())
            # restart
            return next_fn

    async def setup(self):
        try:
            # load secrets
            self.keystore.init()
            # unlock with the PIN code
            # check if we just booted and have less than max attempts
            if self.just_booted and (self.keystore.pin_attempts_left != self.keystore.pin_attempts_max):
                await self.gui.alert("Warning!", 
                    "You only have %d of %d attempts\nto enter correct PIN code!" % (
                        self.keystore.pin_attempts_left, self.keystore.pin_attempts_max
                        ))
            # no need to show the warning every time
            self.just_booted = False
            # or set up the PIN code
            await self.unlock()
        except Exception as e:
            next_fn = await self.handle_exception(e, self.setup)
            await next_fn()

        await self.main()

    async def host_exception_handler(self, e):
        try:
            raise e
        except HostError as ex:
            msg = "%s" % ex
        except:
            b = BytesIO()
            sys.print_exception(e, b)
            msg = b.getvalue().decode()
        res = await self.gui.error(msg, popup=True)

    async def main(self):
        while True:
            try:
                # trigger garbage collector
                gc.collect()
                # show init menu and wait for the next menu
                # any menu returns next menu or
                # None if the same menu should be used
                next_menu = await self.current_menu()
                if next_menu is not None:
                    self.current_menu = next_menu

            except Exception as e:
                next_fn = await self.handle_exception(e, self.setup)
                await next_fn()

    async def initmenu(self):
        # for every button we use an ID
        # to avoid mistakes when editing strings
        # If ID is None - it is a section title, not a button
        buttons = [
            # id, text
            (None, "Key management"),
            (0, "Generate new key"),
            (1, "Enter recovery phrase"),
            (2, "Load key from flash"),
            (None, "Settings"),
            (3, "Developer & USB settings"),
            (4, "Change PIN code"),
            (5, "Lock device"),
        ]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons)

        # process the menu button:
        if menuitem == 0:
            mnemonic = await self.gui.new_mnemonic(gen_mnemonic)
            if mnemonic is not None:
                # load keys using mnemonic and empty password
                self.keystore.set_mnemonic(mnemonic.strip(),"")
                self.wallet_manager.init(self.keystore, self.network)
                return self.mainmenu
        # recover
        elif menuitem == 1:
            mnemonic = await self.gui.recover(bip39.mnemonic_is_valid, bip39.find_candidates)
            if mnemonic is not None:
                # load keys using mnemonic and empty password
                self.keystore.set_mnemonic(mnemonic,"")
                self.wallet_manager.init(self.keystore, self.network)
                self.current_menu = self.mainmenu
                return self.mainmenu
        elif menuitem == 2:
            self.keystore.load_mnemonic()
            # await self.gui.alert("Success!", "Key is loaded from flash!")
            self.wallet_manager.init(self.keystore, self.network)
            return self.mainmenu
        elif menuitem == 3:
            await self.update_devsettings()
        # change pin code
        elif menuitem == 4:
            await self.change_pin()
            await self.gui.alert("Success!", "PIN code is sucessfully changed!")
        # lock device
        elif menuitem == 5:
            await self.lock()
            # go to PIN setup screen
            await self.unlock()
        else:
            print(menuitem,"menu is not implemented yet")
            raise SpecterError("Not implemented")

    async def change_pin(self):
        # get_auth_word function can generate words from part of the PIN
        get_auth_word = self.keystore.get_auth_word
        old_pin = await self.gui.get_pin(get_word=get_auth_word, 
                            title="First enter your old PIN code")
        # check pin - will raise if not valid
        self.keystore.unlock(old_pin)
        new_pin = await self.gui.setup_pin(get_word=get_auth_word)
        self.keystore.change_pin(old_pin, new_pin)

    async def mainmenu(self):
        for host in self.hosts:
            await host.enable()
        # buttons defined by host classes
        # only added if there is a GUI-triggered communication
        host_buttons = [
            (host, host.button) for host in self.hosts if host.button is not None
        ]
        # for every button we use an ID
        # to avoid mistakes when editing strings
        # If ID is None - it is a section title, not a button
        buttons = [
            # id, text
            (None, "Key management"),
            (0, "Wallets"),
            (1, "Master public keys"),
            (None, "Communication"),
        ] + host_buttons + [
            (None, "More"), # delimiter
            (2, "Lock device"),
            (3, "Switch network (%s)" % NETWORKS[self.network]["name"]),
            (4, "Settings"),
        ]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons)

        # process the menu button:
        # wallets
        if menuitem == 0:
            return await self.show_wallets()
        # xpubs
        elif menuitem == 1:
            return await self.show_master_keys()
        # lock device
        elif menuitem == 2:
            await self.lock()
            # go to the unlock screen
            await self.unlock()
        elif menuitem == 3:
            await self.select_network()
        elif menuitem == 4:
            return await self.settingsmenu()
        # if it's a host
        elif hasattr(menuitem, 'get_data'):
            host = menuitem
            cmd, stream = await host.get_data()
            if cmd == host.SIGN_PSBT:
                res = await self.sign_psbt(stream)
                if res is not None:
                    await host.send_psbt(res)
            elif cmd == host.ADD_WALLET:
                # read content, it's small
                desc = stream.read().decode()
                w = self.wallet_manager.parse_wallet(desc)
                res = await self.confirm_new_wallet(w)
                if res:
                    self.wallet_manager.add_wallet(w)
                    return await self.show_wallets()
            elif cmd == host.VERIFY_ADDRESS:
                data = stream.read().decode().replace("bitcoin:","")
                # should be of the form addr?index=N or similar
                if "index=" not in data or "?" not in data:
                    raise SpecterError("Can't verify address with unknown index")
                addr, rest = data.split("?")
                args = rest.split("&")
                idx = None
                for arg in args:
                    if arg.startswith("index="):
                        idx = int(arg[6:])
                        break
                w = self.wallet_manager.find_wallet_from_address(addr, idx)
                await self.gui.show_wallet(w, self.network, idx)
            # probably user cancelled
            elif cmd == None:
                pass
            else:
                # read first 30 bytes and print them to the error
                raise HostError("Unsupported data type:\n%r..." % stream.read(30))
        else:
            print(menuitem)
            raise SpecterError("Not implemented")

    async def sign_psbt(self, stream, remote=False):
        psbt = PSBT.read_from(stream)
        wallet, meta = self.wallet_manager.parse_psbt(psbt=psbt)
        res = await self.gui.confirm_transaction(wallet.name, meta, remote=remote)
        if res:
            # fill derivation paths from proprietary fields
            wallet.update_gaps(psbt=psbt)
            wallet.save(self.keystore)
            psbt = wallet.fill_psbt(psbt, self.keystore.fingerprint)
            self.keystore.sign_psbt(psbt)
            return psbt

    async def confirm_new_wallet(self, w):
        keys = [{"key": k, "mine": self.keystore.owns(k)} for k in w.get_keys()]
        if not any([k["mine"] for k in keys]):
            raise SpecterError("None of the keys belong to the device")
        return await self.gui.confirm_new_wallet(w.name, w.policy, keys)

    async def select_network(self):
        # dict is unordered unfortunately, so we need to use hardcoded arr
        nets = ["main", "test", "regtest", "signet"]
        buttons = [(net, NETWORKS[net]["name"]) for net in nets]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons, last=(255, None))
        if menuitem != 255:
            self.set_network(menuitem)

    def set_network(self, net):
        if net not in NETWORKS:
            raise SpecterError("Invalid network")
        self.network = net
        self.gui.set_network(net)
        # save
        with open(self.path+"/network", "w") as f:
            f.write(net)
        if self.keystore.is_ready:
            # load wallets for this network
            self.wallet_manager.init(self.keystore, self.network)

    def load_network(self, path):
        network = 'test'
        try:
            with open(path+"/network","r") as f:
                network = f.read()
                if network not in NETWORKS:
                    raise SpecterError("Invalid network")
        except:
            pass
        self.set_network(network)

    async def settingsmenu(self):
        buttons = [
            # id, text
            (None, "Key management"),
            (0, "Reckless"),
            (2, "Enter a bip39 password"),
            (None, "Security"), # delimiter
            (3, "Change PIN code"),
            (4, "Developer & USB"),
        ]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons, last=(255, None))

        # process the menu button:
        # back button
        if menuitem == 255:
            return self.mainmenu
        elif menuitem == 0:
            return await self.recklessmenu()
        elif menuitem == 2:
            pwd = await self.gui.get_input()
            if pwd is None:
                return self.mainmenu
            self.keystore.set_mnemonic(password=pwd)
            self.wallet_manager.init(self.keystore, self.network)
        elif menuitem == 3:
            await self.change_pin()
            await self.gui.alert("Success!", "PIN code is sucessfully changed!")
            return self.mainmenu
        elif menuitem == 4:
            await self.update_devsettings()
        else:
            print(menuitem)
            raise SpecterError("Not implemented")

    async def update_devsettings(self):
        res = await self.gui.devscreen(dev=self.dev, usb=self.usb)
        if res is not None:
            self.update_config(**res)
            if await self.gui.prompt("Reboot required!", "Changing USB mode requires to reboot the device. Proceed?"):
                reboot()

    async def recklessmenu(self):
        """Manage storage and display of the recovery phrase"""
        buttons = [
            # id, text
            (None, "Key management"),
            (0, "Save key to flash"),
            (1, "Load key from flash"),
            (2, "Delete key from flash"),
            (3, "Show recovery phrase"),
        ]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons, last=(255, None))

        # process the menu button:
        # back button
        if menuitem == 255:
            return self.settingsmenu
        elif menuitem == 0:
            self.keystore.save_mnemonic()
            await self.gui.alert("Success!", "Your key is stored in flash now.")
            return self.settingsmenu
        elif menuitem == 1:
            self.keystore.load_mnemonic()
            await self.gui.alert("Success!", "Your key is loaded.")
            return self.mainmenu
        elif menuitem == 2:
            self.keystore.delete_mnemonic()
            await self.gui.alert("Success!", "Your key is deleted from flash.")
            return self.mainmenu
        elif menuitem == 3:
            await self.gui.show_mnemonic(self.keystore.mnemonic)
        else:
            raise SpecterError("Invalid menu")

    async def show_wallets(self):
        buttons = [(None, "Your wallets")]
        buttons += [(i, w.name) for i, w in enumerate(self.wallet_manager.wallets)]
        menuitem = await self.gui.menu(buttons, last=(255,None))
        if menuitem == 255:
            return self.mainmenu
        else:
            w = self.wallet_manager.wallets[menuitem]
            # pass wallet and network
            cmd = await self.gui.show_wallet(w, self.network, idx=w.unused_recv)
            if cmd == DELETE:
                conf = await self.gui.prompt("Delete wallet?", "You are deleting wallet \"%s\".\nAre you sure you want to do it?" % w.name)
                if conf:
                    self.wallet_manager.delete_wallet(w)
                return self.show_wallets
            elif cmd == EDIT:
                name = await self.gui.get_input(title="Enter new wallet name", 
                            note="", suggestion=w.name)
                if name is not None and name != w.name and name != "":
                    w.name = name
                    w.save(self.keystore)
                return self.show_wallets

    async def lock(self):
        # lock the keystore
        self.keystore.lock()
        # disable hosts
        for host in self.hosts:
            await host.disable()
        # disable usb and dev
        set_usb_mode(False, False)

    async def unlock(self):
        """
        - setup PIN if not set
        - enter PIN if set
        """
        # get_auth_word function can generate words from part of the PIN
        get_auth_word = self.keystore.get_auth_word
        # pin is not set - choose one
        if not self.keystore.is_pin_set:
            pin = await self.gui.setup_pin(get_word=get_auth_word)
            self.keystore.set_pin(pin)

        # if keystore is locked - ask for PIN code
        while self.keystore.is_locked:
            pin = await self.gui.get_pin(get_word=get_auth_word)
            self.keystore.unlock(pin)

        # now keystore is unlocked - we can proceed
        # load configuration
        self.load_config()
        set_usb_mode(usb=self.usb, dev=self.dev)

    def load_config(self):
        try:
            config, _ = self.keystore.load_aead(self.path+"/settings", 
                                                self.keystore.enc_secret)
            config = json.loads(config.decode())
        except Exception as e:
            print(e)
            config = {"dev": self.dev, "usb": self.usb}
            self.keystore.save_aead(self.path+"/settings", 
                                    adata=json.dumps(config).encode(),
                                    key=self.keystore.enc_secret)
        self.dev = config["dev"]
        self.usb = config["usb"]

    def update_config(self, usb=False, dev=False):
        config = {
            "usb": usb,
            "dev": dev,
        }
        self.keystore.save_aead(self.path+"/settings", 
                                adata=json.dumps(config).encode(),
                                key=self.keystore.enc_secret)
        self.usb = usb
        self.dev = dev
        set_usb_mode(usb=self.usb, dev=self.dev)

    # host related commands
    def get_fingerprint(self) -> bytes:
        if self.keystore.is_locked:
            raise SpecterError("Device is locked")
        return self.keystore.fingerprint

    def get_xpub(self, path:list):
        if self.keystore.is_locked:
            raise SpecterError("Device is locked")
        xpub = self.keystore.get_xpub(bip32.path_to_str(path))
        return xpub

    async def showaddr(self, paths:list, script_type:str, redeem_script=None) -> str:
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
                address = script.p2sh(
                            script.p2wsh(redeem_script)
                          ).address(NETWORKS[self.network])
            else:
                raise HostError("Unsupported script type: %s" % script_type)
        # in our wallets every key 
        # has the same two last indexes for derivation
        path = paths[0]
        if not path.startswith(b"m/"):
            path = b"m"+path[8:]
        derivation = bip32.parse_path(path.decode())

        # if not multisig:
        if address is None and len(paths)==1:
            pub = self.keystore.get_xpub(derivation)
            if script_type == b"wpkh":
                address = script.p2wpkh(pub).address(NETWORKS[self.network])
            elif script_type == b"sh-wpkh":
                address = script.p2sh(
                            script.p2wpkh(pub).address(NETWORKS[self.network])
                          )
            else:
                raise HostError("Unsupported script type: %s" % script_type)

        if len(derivation) >= 2:
            derivation = derivation[-2:]
        else:
            raise HostError("Invalid derivation")
        if address is None:
            raise HostError("Can't derive address. Provide redeem script.")
        try:
            change = bool(derivation[0])
            w = self.wallet_manager.find_wallet_from_address(address, derivation[1], change=change)
        except BaseError as e:
            raise HostError("%s" % e)
        await self.gui.show_wallet(w, self.network, derivation[1], change=change, remote=True)
        return address

    async def show_master_keys(self, show_all=False):
        net = NETWORKS[self.network]
        buttons = [
            (None, "Recommended"),
            ("m/84h/%dh/0h" % net["bip32"], "Single key"),
            ("m/48h/%dh/0h/2h" % net["bip32"], "Multisig"),
            (None, "Other keys"),
        ]
        if show_all:
            buttons += [
                ("m/84h/%dh/0h" % net["bip32"], "Single Native Segwit\nm/84h/%dh/0h" % net["bip32"]),
                ("m/49h/%dh/0h" % net["bip32"], "Single Nested Segwit\nm/49h/%dh/0h" % net["bip32"]),
                ("m/48h/%dh/0h/2h" % net["bip32"], "Multisig Native Segwit\nm/48h/%dh/0h/2h" % net["bip32"]),
                ("m/48h/%dh/0h/1h" % net["bip32"], "Multisig Nested Segwit\nm/48h/%dh/0h/1h" % net["bip32"]),
            ]
        else:
            buttons += [
                (0, "Show more keys"),
                (1, "Enter custom derivation")
            ]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons, last=(255, None))

        # process the menu button:
        # back button
        if menuitem == 255:
            # hide keys on first "back"
            return self.show_master_keys if show_all else self.mainmenu
        elif menuitem == 0:
            return await self.show_master_keys(show_all=True)
        elif menuitem == 1:
            der = await self.gui.get_derivation()
            if der is not None:
                await self.show_xpub(der)
                return self.show_master_keys
        else:
            await self.show_xpub(menuitem)
            return self.show_master_keys
        return self.mainmenu

    async def show_xpub(self, derivation):
        derivation = derivation.rstrip("/")
        net = NETWORKS[self.network]
        xpub = self.keystore.get_xpub(derivation)
        ver = bip32.detect_version(derivation, default="xpub",
                        network=net)
        canonical = xpub.to_base58(net["xpub"])
        slip132 = xpub.to_base58(ver)
        if slip132 == canonical:
            slip132 = None
        prefix = "[%s%s]" % (
            hexlify(self.keystore.fingerprint).decode(), 
            derivation[1:]
        )
        await self.gui.show_xpub(xpub=canonical, 
                                slip132=slip132, 
                                prefix=prefix)
