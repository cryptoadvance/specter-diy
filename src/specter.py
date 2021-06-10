import sys
import gc
import json
from io import BytesIO
import asyncio

from platform import (
    CriticalErrorWipeImmediately,
    set_usb_mode,
    reboot,
    fpath,
    maybe_mkdir,
    file_exists,
    wipe,
    get_version,
    get_battery_status,
)
from hosts import Host, HostError
from app import BaseApp
from bitcoin import bip39
from bitcoin.networks import NETWORKS

# small helper functions
from helpers import gen_mnemonic, fix_mnemonic, load_apps
from errors import BaseError


class SpecterError(BaseError):
    NAME = "Specter error"


class Specter:
    """Specter class.
    Call .start() method to register in the event loop
    It will then call the .setup() and .main() functions to display the GUI
    """
    usb = False
    def __init__(self, gui, keystores, hosts, apps, settings_path, network="main"):
        self.hosts = hosts
        self.keystores = keystores
        self.keystore = None
        if len(keystores) == 1:
            # instantiate the keystore class
            self.keystore = keystores[0]()
        self.network = network
        self.gui = gui
        self.path = settings_path
        self.current_menu = self.initmenu
        self.dev = False
        self.apps = apps

    def start(self):
        # register battery monitor (runs every 3 seconds)
        self.gui.set_battery_callback(get_battery_status, 3000)
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
        self.gui.hide_loader()
        try:
            raise exception
        except CriticalErrorWipeImmediately as e:
            # show error
            await self.gui.error("Critical error, the device will be wiped.\n\n%s" % e)
            self.gui.show_loader(title="Wiping the device...")
            # wipe everything and reboot
            self.wipe()
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

    async def select_keystore(self):
        # if we have fixed keystore - just use it
        if len(self.keystores) == 1:
            self.keystore = self.keystores[0]()
            return
        # checking the first available keystore
        keystore_cls = None
        # TODO: show some screen here if none are available
        while keystore_cls is None:
            for keystore in self.keystores:
                if keystore.is_available():
                    keystore_cls = keystore
                    break
            # if none are available just wait for it
            # if keystore_cls is None:
            #     await asyncio.sleep_ms(50)
        self.keystore = keystore_cls()

    async def setup(self):
        try:
            # check if the user already selected the keystore class
            if self.keystore is None:
                await self.select_keystore()

            if self.keystore is not None:
                self.load_network(self.path, self.network)

            # load secrets
            await self.keystore.init(self.gui.show_screen(), self.gui.show_loader)
            # unlock with PIN or set up the PIN code
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

    def init_apps(self):
        for app in self.apps:
            app.init(self.keystore, self.network, self.gui.show_loader, self.cross_app_communicate)

    async def cross_app_communicate(self, stream, app:str=None):
        return await self.process_host_request(stream, popup=False, appname=app)

    async def initmenu(self):
        # for every button we use an ID
        # to avoid mistakes when editing strings
        # If ID is None - it is a section title, not a button
        buttons = [
            # id, text
            (None, "Key management"),
            (0, "Generate new key"),
            (1, "Enter recovery phrase"),
        ]
        if self.keystore.is_key_saved and self.keystore.load_button:
            buttons.append((2, self.keystore.load_button))
        buttons += [(None, "Settings"), (3, "Device settings")]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons)

        # process the menu button:
        if menuitem == 0:
            mnemonic = await self.gui.new_mnemonic(gen_mnemonic, bip39.WORDLIST, fix_mnemonic)
            if mnemonic is not None:
                # load keys using mnemonic and empty password
                self.keystore.set_mnemonic(mnemonic.strip(), "")
                self.init_apps()
                return self.mainmenu
        # recover
        elif menuitem == 1:
            mnemonic = await self.gui.recover(
                bip39.mnemonic_is_valid, bip39.find_candidates, fix_mnemonic
            )
            if mnemonic is not None:
                # load keys using mnemonic and empty password
                self.keystore.set_mnemonic(mnemonic, "")
                self.init_apps()
                self.current_menu = self.mainmenu
                return self.mainmenu
        elif menuitem == 2:
            # try to load key, if user cancels -> return
            res = await self.keystore.load_mnemonic()
            if not res:
                return
            # await self.gui.alert("Success!", "Key is loaded from flash!")
            self.init_apps()
            return self.mainmenu
        elif menuitem == 3:
            await self.update_devsettings()
        # lock device
        elif menuitem == 5:
            await self.lock()
            # go to PIN setup screen
            await self.unlock()
        else:
            print(menuitem, "menu is not implemented yet")
            raise SpecterError("Not implemented")

    async def mainmenu(self):
        for host in self.hosts:
            await host.enable()
        # buttons defined by host classes
        # only added if there is a GUI-triggered communication
        host_buttons = [
            (host, host.button) for host in self.hosts if host.button is not None and host.is_enabled
        ]
        # buttons defined by app classes
        app_buttons = [(app, app.button) for app in self.apps if app.button is not None]
        # for every button we use an ID
        # to avoid mistakes when editing strings
        # If ID is None - it is a section title, not a button
        buttons = (
            [
                # id, text
                (None, "Applications")
            ]
            + app_buttons
            + [(None, "Communication")]
            + host_buttons
            + [(None, "More")]  # delimiter
        )
        if hasattr(self.keystore, "lock"):
            buttons += [(2, "Lock device")]
        buttons += [(3, "Settings")]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons)

        # process the menu button:
        # lock device
        if menuitem == 2 and hasattr(self.keystore, "lock"):
            await self.lock()
            # go to the unlock screen
            await self.unlock()
        elif menuitem == 3:
            return await self.settingsmenu()
        elif isinstance(menuitem, BaseApp) and hasattr(menuitem, "menu"):
            app = menuitem
            # stay in this menu while something is returned
            while await app.menu(self.gui.show_screen()):
                pass
        # if it's a host
        elif isinstance(menuitem, Host) and hasattr(menuitem, "get_data"):
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

    async def settingsmenu(self):
        net = NETWORKS[self.network]["name"]
        buttons = [
            # id, text
            (None, "Network"),
            (5, "Switch network (%s)" % net),
            (None, "Key management"),
        ]
        if self.keystore.storage_button is not None:
            buttons.append((1, self.keystore.storage_button))
        buttons.append((2, "Enter BIP-39 password"))
        if hasattr(self.keystore, "show_mnemonic"):
            buttons.append((3, "Show recovery phrase"))
        buttons.extend([(None, "Security"), (4, "Device settings")])  # delimiter
        # wait for menu selection
        menuitem = await self.gui.menu(buttons, last=(255, None), note="Firmware version %s" % get_version())

        # process the menu button:
        # back button
        if menuitem == 255:
            return self.mainmenu
        elif menuitem == 1:
            await self.keystore.storage_menu()
        elif menuitem == 2:
            pwd = await self.gui.get_input()
            if pwd is None:
                return self.settingsmenu
            self.keystore.set_mnemonic(password=pwd)
            self.init_apps()
        elif menuitem == 3:
            await self.keystore.show_mnemonic()
        elif menuitem == 4:
            await self.update_devsettings()
        elif menuitem == 5:
            await self.select_network()
        else:
            print(menuitem)
            raise SpecterError("Not implemented")
        return self.settingsmenu

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
            net = 'main'
        self.network = net
        self.gui.set_network(net)
        # save
        with open(self.path + "/network", "w") as f:
            f.write(net)
        if self.keystore.is_ready:
            # load wallets for this network
            self.init_apps()

    def load_network(self, path, network="main"):
        try:
            with open(path + "/network", "r") as f:
                network = f.read()
        except:
            pass
        self.set_network(network)

    async def update_devsettings(self):
        buttons = [
            (None, "Communication settings")
        ] + [
            (host, host.settings_button)
            for host in self.hosts
            if host.settings_button is not None
        ] + [
            (None, "Global settings"),
        ]
        if hasattr(self.keystore, "lock"):
            buttons.extend([(3, "Change PIN code")])
        buttons += [
            (456, "Reboot"),
            (123, "Wipe the device", True, 0x951E2D),
        ]
        while True:
            menuitem = await self.gui.menu(buttons,
                                      title="Device settings",
                                      note="Firmware version %s" % get_version(),
                                      last=(255, None)
            )
            if menuitem == 255:
                return
            elif menuitem == 456:
                if await self.gui.prompt(
                    "Reboot the device?",
                    "\n\nAre you sure?",
                ):
                    reboot()
                return
            # WIPE
            elif menuitem == 123:
                if await self.gui.prompt(
                    "Wiping the device will erase everything in the internal storage!",
                    "This includes multisig wallet files, keys, apps data etc.\n\n"
                    "But it doesn't include files stored on SD card or smartcard.\n\n"
                    "Are you sure?",
                ):
                    self.wipe()
                return
            elif menuitem == 3:
                await self.keystore.change_pin()
                return
            elif isinstance(menuitem, Host):
                reboot_required = await menuitem.settings_menu(self.gui.show_screen(), self.keystore)
                if reboot_required:
                    if await self.gui.prompt(
                        "Reboot required!",
                        "Settings have been updated and will become active after reboot.\n\n"
                        "Do you want to reboot now?",
                    ):
                        reboot()
            else:
                print(menuitem)
                raise SpecterError("Not implemented")

    def wipe(self):
        # TODO: wipe the smartcard as well?
        # platform.wipe
        wipe()

    async def lock(self):
        # lock the keystore
        if hasattr(self.keystore, "lock"):
            self.keystore.lock()
        # disable hosts
        for host in self.hosts:
            await host.disable()

    async def unlock(self):
        """
        - setup PIN if not set
        - enter PIN if set
        """
        await self.keystore.unlock()
        # now keystore is unlocked - we can load hosts configs
        for host in self.hosts:
            host.load_settings(self.keystore)

    async def process_host_request(self, stream, popup=True, appname=None):
        """
        This method is called whenever we got data from the host.
        It tries to find a proper app and pass the stream with data to it.
        """
        self.gui.show_loader(title="Processing host data...")
        res = None
        try:
            matching_apps = []
            if appname is not None:
                for app in self.apps:
                    if app.name == appname:
                        matching_apps.append(app)
            else:
                for app in self.apps:
                    stream.seek(0)
                    # check if the app can process this stream
                    if app.can_process(stream):
                        matching_apps.append(app)
            if len(matching_apps) == 0:
                raise HostError("Can't find matching app for this request")
            # TODO: if more than one - ask which one to use
            if len(matching_apps) > 1:
                raise HostError(
                    "Not sure what app to use...\n\nThere are %d" % len(matching_apps)
                )
            stream.seek(0)
            app = matching_apps[0]
            res = await app.process_host_command(stream, self.gui.show_screen(popup))
        except Exception as e:
            if isinstance(e, BaseError):
                # error that has a meaningfull message, will be sent to the host
                raise HostError(str(e))
            else:
                # converted to "unknown error" on the host
                raise e
        finally:
            self.gui.hide_loader()
        return res
