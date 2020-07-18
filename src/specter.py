import sys
import gc
import json
from binascii import hexlify, unhexlify
from io import BytesIO
import asyncio

from keystore import FlashKeyStore
from platform import CriticalErrorWipeImmediately, set_usb_mode, reboot
from hosts import Host, HostError
from app import BaseApp
from bitcoin import bip39
from bitcoin.networks import NETWORKS
# small helper functions
from helpers import gen_mnemonic
from errors import BaseError


class SpecterError(BaseError):
    NAME = "Specter error"


class Specter:
    """Specter class.
    Call .start() method to register in the event loop
    It will then call the .setup() and .main() functions to display the GUI
    """

    def __init__(self, gui, keystore, hosts, apps,
                 settings_path, network='test'):
        self.hosts = hosts
        self.keystore = keystore
        self.gui = gui
        self.path = settings_path
        self.load_network(self.path, network)
        self.current_menu = self.initmenu
        self.just_booted = True
        self.usb = False
        self.dev = False
        self.apps = apps

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
            # wipe all apps
            for app in self.apps:
                app.wipe()
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
            errmsg = "Something unexpected happened...\n\n"
            errmsg += b.getvalue().decode()
            await self.gui.error(errmsg)
            # restart
            return next_fn

    async def setup(self):
        try:
            # load secrets
            self.keystore.init()
            # unlock with the PIN code
            # check if we just booted and have less than max attempts
            pin_left = self.keystore.pin_attempts_left
            pin_max = self.keystore.pin_attempts_max
            if (self.just_booted and pin_left != pin_max):
                await self.gui.alert("Warning!",
                                     "You only have %d of %d attempts\n"
                                     "to enter correct PIN code!" % (
                                         pin_left, pin_max
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
                self.keystore.set_mnemonic(mnemonic.strip(), "")
                for app in self.apps:
                    app.init(self.keystore, self.network)
                return self.mainmenu
        # recover
        elif menuitem == 1:
            mnemonic = await self.gui.recover(bip39.mnemonic_is_valid,
                                              bip39.find_candidates)
            if mnemonic is not None:
                # load keys using mnemonic and empty password
                self.keystore.set_mnemonic(mnemonic, "")
                for app in self.apps:
                    app.init(self.keystore, self.network)
                self.current_menu = self.mainmenu
                return self.mainmenu
        elif menuitem == 2:
            self.keystore.load_mnemonic()
            # await self.gui.alert("Success!", "Key is loaded from flash!")
            for app in self.apps:
                app.init(self.keystore, self.network)
            return self.mainmenu
        elif menuitem == 3:
            await self.update_devsettings()
        # change pin code
        elif menuitem == 4:
            await self.change_pin()
            await self.gui.alert("Success!",
                                 "PIN code is sucessfully changed!")
        # lock device
        elif menuitem == 5:
            await self.lock()
            # go to PIN setup screen
            await self.unlock()
        else:
            print(menuitem, "menu is not implemented yet")
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
            (host, host.button)
            for host in self.hosts
            if host.button is not None
        ]
        # buttons defined by app classes
        app_buttons = [
            (app, app.button)
            for app in self.apps
            if app.button is not None
        ]
        # for every button we use an ID
        # to avoid mistakes when editing strings
        # If ID is None - it is a section title, not a button
        net = NETWORKS[self.network]["name"]
        buttons = [
            # id, text
            (None, "Applications"),
        ] + app_buttons + [
            (None, "Communication"),
        ] + host_buttons + [
            (None, "More"),  # delimiter
            (2, "Lock device"),
            (3, "Switch network (%s)" % net),
            (4, "Settings"),
        ]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons)

        # process the menu button:
        # lock device
        if menuitem == 2:
            await self.lock()
            # go to the unlock screen
            await self.unlock()
        elif menuitem == 3:
            await self.select_network()
        elif menuitem == 4:
            return await self.settingsmenu()
        elif isinstance(menuitem, BaseApp) and hasattr(menuitem, 'menu'):
            app = menuitem
            # stay in this menu while something is returned
            while await app.menu(self.gui.show_screen()):
                pass
        # if it's a host
        elif isinstance(menuitem, Host) and hasattr(menuitem, 'get_data'):
            host = menuitem
            stream = await host.get_data()
            # probably user cancelled
            if stream is not None:
                # check against all apps
                res = await self.process_host_request(stream, popup=False)
                if res is not None:
                    await host.send_data(*res)
        else:
            print(menuitem)
            raise SpecterError("Not implemented")

    async def process_host_request(self, stream, popup=True):
        """
        This method is called whenever we got data from the host.
        It tries to find a proper app and pass the stream with data to it.
        """
        matching_apps = []
        for app in self.apps:
            stream.seek(0)
            # check if the app can process this stream
            if app.can_process(stream):
                matching_apps.append(app)
        if len(matching_apps) == 0:
            raise HostError("Host command is not recognized")
        # TODO: if more than one - ask which one to use
        if len(matching_apps) > 1:
            raise HostError(
                "Not sure what app to use... "
                "There are %d" % len(matching_apps))
        stream.seek(0)
        app = matching_apps[0]
        return await app.process_host_command(stream,
                                              self.gui.show_screen(popup))

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
            for app in self.apps:
                app.init(self.keystore, self.network)

    def load_network(self, path, network='test'):
        try:
            with open(path+"/network", "r") as f:
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
            (2, "Enter password"),
            (None, "Security"),  # delimiter
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
            for app in self.apps:
                app.init(self.keystore, self.network)
        elif menuitem == 3:
            await self.change_pin()
            await self.gui.alert("Success!",
                                 "PIN code is sucessfully changed!")
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
            if await self.gui.prompt("Reboot required!",
                                     "Changing USB mode requires to "
                                     "reboot the device. Proceed?"):
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
            await self.gui.alert("Success!",
                                 "Your key is stored in flash now.")
            return self.settingsmenu
        elif menuitem == 1:
            self.keystore.load_mnemonic()
            await self.gui.alert("Success!",
                                 "Your key is loaded.")
            return self.mainmenu
        elif menuitem == 2:
            self.keystore.delete_mnemonic()
            await self.gui.alert("Success!",
                                 "Your key is deleted from flash.")
            return self.mainmenu
        elif menuitem == 3:
            await self.gui.show_mnemonic(self.keystore.mnemonic)
        else:
            raise SpecterError("Invalid menu")

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
        # get_auth_word function can
        # generate words from part of the PIN
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
