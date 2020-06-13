import sys, gc
from binascii import hexlify
from io import BytesIO
import asyncio

from keystore import FlashKeyStore, KeyStoreError
from platform import CriticalErrorWipeImmediately
from hosts import HostError
from bitcoin import ec, psbt, bip32, bip39
from bitcoin.networks import NETWORKS
# small helper functions
from helpers import gen_mnemonic

class SpecterError(Exception):
    pass

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

    def load_network(self, path):
        network = 'test'
        try:
            with open(path+"/network","r") as f:
                network = f.read()
                if network not in NETWORKS:
                    raise SpecterError("Invalid network")
        except:
            with open(path+"/network", "w") as f:
                f.write(network)
        self.network = network

    def start(self):
        # start the GUI
        self.gui.start()
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
        except (SpecterError, HostError, KeyStoreError) as e:
            # show error
            await self.gui.error("%s" % e)
            # restart
            return next_fn

        # show trace for unexpected errors
        except Exception as e:
            print(e)
            b = BytesIO()
            sys.print_exception(e, b)
            await self.gui.error("Something bad happened...\n\n%s" % b.getvalue().decode())
            # restart
            return next_fn

    async def setup(self):
        try:
            # load secrets
            self.keystore.init()
            # unlock with the PIN code if needed
            # or set up the PIN code
            await self.unlock()
            # register coroutines for all hosts
            for host in self.hosts:
                # When you start the host
                # pass command handler class to it
                # In this case it's us.
                host.start(self)
        except Exception as e:
            next_fn = await self.handle_exception(e, self.setup)
            await next_fn()

        await self.main()

    async def main(self):
        while True:
            try:
                # trigger garbage collector
                gc.collect()
                # show main menu and wait for interactions
                await self.initmenu()

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
            (3, "Hardware settings"),
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
                self.keystore.load_mnemonic(mnemonic,"")
                self.wallet_manager.init(self.keystore, self.network)
                await self.mainmenu()
        # recover
        elif menuitem == 1:
            mnemonic = await self.gui.recover(bip39.mnemonic_is_valid, bip39.find_candidates)
            if mnemonic is not None:
                # load keys using mnemonic and empty password
                self.keystore.load_mnemonic(mnemonic,"")
                self.wallet_manager.init(self.keystore, self.network)
                await self.mainmenu()
        # change pin code
        elif menuitem == 4:
            self.keystore.unset_pin()
            # go to PIN setup screen
            return await self.unlock()
        # lock device
        elif menuitem == 5:
            self.keystore.lock()
            # go to PIN setup screen
            return await self.unlock()
        else:
            print(menuitem,"menu is not implemented yet")
            raise SpecterError("Not implemented")

    async def mainmenu(self):
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
            (None, "PIN management".upper()),
            (0, "Lock device"),
            (1, "Change PIN code"),
            (None, "Advanced".upper()), # delimiter
            (2, "Configuration information"),
        ]
        # if non-bidirectional hosts are available
        # add corresponding section
        if len(host_buttons) > 0:
            buttons = [(None, "Sign Transaction".upper())]+host_buttons+buttons
        # wait for menu selection
        menuitem = await self.gui.menu(buttons)

        # process the menu button:
        # lock device
        if menuitem == 0:
            # lock the SE
            self.keystore.lock()
            # go to the unlock screen
            return await self.unlock()
        # change PIN code
        elif menuitem == 1:
            # unset PIN
            self.keystore.unset_pin()
            # go to PIN setup screen
            return await self.unlock()
        # display config menu
        elif menuitem == 2:
            await self.browse_config()
        # if it's a host
        elif hasattr(menuitem, 'get_tx'):
            host = menuitem
            # get_tx function returns streams:
            # (stream with binary psbt, [list of auth signatures])
            # TODO: await!
            raw_tx_stream, sigs = await host.get_tx()
            # try to sign
            tx = await self.sign_transaction(raw_tx_stream, sigs)
            if tx is None:
                # notify the host that user didn't confirm
                host.user_canceled()
                return
            # send to the host, fingerprint is nice to have for saving PSBT file
            msg = await host.send_tx(tx, hexlify(self.keystore.fingerprint).decode())
            # if we got a message from host - show it to the user
            if msg is not None:
                await self.gui.alert("Success!", msg)
        else:
            print(menuitem)
            raise SpecterError("Not implemented")

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

        # if card is locked - ask for PIN code
        while self.keystore.is_locked:
            pin = await self.gui.get_pin(get_word=get_auth_word)
            if not self.keystore.unlock(pin):
                await self.gui.error("Invalid PIN code!")

        # now card is unlocked - we can proceed

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

    # remote means that this command and corresponding GUI was not triggered
    # by the user on the GUI, but from the host directly (USB)
    async def sign_transaction(self, raw_tx_stream, remote=False):
        # parse psbt transaction
        tx = psbt.PSBT.read_from(raw_tx_stream)
        raw_tx_stream.close()
        # get GUI-friendly dict and list
        tx_data = self.wallet_manager.verify_tx(tx)
        # ask the user
        res = await self.gui.display_transaction(tx_data, 
                                                 self.network,
                                                 popup=remote)
        # if it was triggered by the host
        # close the request window
        if remote:
            self.gui.close_popup()
        # if user confirmed - sign and save / show
        if res:
            # sign transaction
            self.keystore.sign(tx, sigs)
            return tx
