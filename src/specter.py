import sys
import os
import gc
import json
from io import BytesIO
import asyncio

import platform
from platform import (
    CriticalErrorWipeImmediately,
    reboot,
    maybe_mkdir,
    wipe,
    get_version,
    get_git_info,
    get_battery_status,
    get_build_type,
    get_firmware_boot_mode,
    get_flash_read_protection_status,
    get_flash_write_protection_status,
)
from hosts import Host, HostError
from app import BaseApp
from embit import bip39
from embit.liquid.networks import NETWORKS
from gui.screens.settings import HostSettings
from gui.screens.mnemonic import MnemonicPrompt
from gui.screens import Prompt, Progress
from keystore.flash import SD_FILE_PREFIX

# bitbox_backup / bitbox_sd are imported lazily inside the BitBox import
# flow so they (and their embit.bip39 dependency) only occupy RAM when a
# BitBox backup is actually being imported - same pattern as the lazy
# qrencoder import in hosts/sd.py.

# small helper functions
from helpers import gen_mnemonic, fix_mnemonic, conv_time
from errors import BaseError


class SpecterError(BaseError):
    NAME = "Specter error"


class Specter:
    """Specter class.
    Call .start() method to register in the event loop
    It will then call the .setup() and .main() functions to display the GUI
    """
    SETTINGS_DIR = None
    # global settings
    GLOBAL = {}

    def __init__(self, gui, keystores, hosts, apps, settings_path, network="main"):
        # so hosts can call methods of Specter
        Host.parent = self
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

    def _firmware_note(self, include_details=False):
        primary_note = "Firmware version %s" % get_version()

        if not include_details:
            return primary_note

        sections = [primary_note]

        repo, branch, commit = get_git_info()
        repo_details = []
        if repo != "unknown":
            repo_details.append("Repo: %s" % repo)
        if branch != "unknown":
            repo_details.append("Branch: %s" % branch)
        if commit != "unknown":
            repo_details.append("Commit: %s" % commit)
        if repo_details:
            sections.append("\n".join(repo_details))

        def _format_status(value):
            if isinstance(value, str) and value:
                return value[0].upper() + value[1:]
            return value

        boot_mode = get_firmware_boot_mode()
        if boot_mode != "unknown":
            boot_mode_note = "Firmware mode: %s" % _format_status(boot_mode)
        else:
            boot_mode_note = "Firmware mode: Unknown"
        sections.append(boot_mode_note)

        read_protect = get_flash_read_protection_status()
        if read_protect != "unknown":
            read_note = "Read protection: %s" % _format_status(read_protect)
        else:
            read_note = "Read protection: Unknown"
        sections.append(read_note)

        write_protect = get_flash_write_protection_status()
        if write_protect != "unknown":
            write_note = "Write protection: %s" % _format_status(write_protect)
        else:
            write_note = "Write protection: Unknown"
        sections.append(write_note)

        build_type = get_build_type()
        if build_type == "unknown":
            build_note = "Build type: Unknown"
        else:
            build_note = "Build type: %s" % _format_status(build_type)
        sections.append(build_note)

        return "\n\n".join(sections)

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
        await self.gui.error(msg, popup=True)

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

    async def cross_app_communicate(self, stream, app:str=None, show_fn=None):
        if app == "": # root
            data = stream.read()
            if data.startswith(b"set_mnemonic "):
                mnemonic = data[len("set_mnemonic "):].decode()
                confirm = await self.gui.prompt(
                        "Load new mnemonic?",
                        "\nApp requested to load new mnemonic\n"
                        "Do you want to continue?\n\n"
                        "You will need to reboot the device to get back"
                        " to your current mnemonic.",
                )
                if confirm:
                    return self.set_mnemonic(mnemonic)
                else:
                    return True
            raise SpecterError("Invalid command '%s'" % data)
        return await self.process_host_request(stream, popup=False, appname=app, show_fn=show_fn)

    async def initmenu(self):
        # only enable passive hosts
        for host in self.hosts:
            if host.button:
                await host.enable()
        # for every button we use an ID
        # to avoid mistakes when editing strings
        # If ID is None - it is a section title, not a button
        buttons = [
            # id, text
            (None, "Key management"),
            (0, "Generate new key"),
            (1, "Enter recovery phrase"),
            (777, "Import recovery phrase"),
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
                return self.set_mnemonic(mnemonic, "")
        # recover
        elif menuitem == 1:
            mnemonic = await self.gui.recover(
                bip39.mnemonic_is_valid, bip39.find_candidates, fix_mnemonic
            )
            if mnemonic is not None:
                # load keys using mnemonic and empty password
                return self.set_mnemonic(mnemonic, "")
        elif menuitem == 2:
            # try to load key, if user cancels -> return
            res = await self.keystore.load_mnemonic()
            if not res:
                return
            await self.gui.alert("Success!", "Key is loaded!")
            self.init_apps()
            return self.mainmenu
        elif menuitem == 3:
            await self.update_devsettings()
        elif menuitem == 777:
            return await self.import_mnemonic()
        # lock device
        elif menuitem == 5:
            await self.lock()
            # go to PIN setup screen
            await self.unlock()
        else:
            print(menuitem, "menu is not implemented yet")
            raise SpecterError("Not implemented")

    # sentinel value for the BitBox microSD backup entry in the import
    # menu below - not a real Host instance, handled as a special case.
    BITBOX_BACKUP = "bitbox_backup"
    # Same cap as bitbox_sd.MAX_LIST_ENTRIES: an adversarial card could
    # put thousands of entries at the SD root, and enumerating all of
    # them would cause unbounded memory use. The "Format entire SD card"
    # option in _sdcard_delete_menu() is the tool for wiping everything
    # indiscriminately, so silently stopping after this many is fine.
    _SDCARD_LIST_MAX_ENTRIES = 200

    @staticmethod
    def _bitbox_backup_dirs_or_none():
        """Best-effort presence check: returns the list of candidate BitBox
        backup directory names found on the card, or None if there is no
        card, it can't be read, or it has no bitbox02/ directory.

        Used only to decide whether "BitBox microSD backup" is worth
        offering as an import source at all - offering it unconditionally
        makes no sense if there's nothing to import, and this way the
        "not encrypted" warning is only ever shown once a backup has
        actually been found, not speculatively. Never raises: any reason
        the card can't be read here just means the option isn't offered;
        the real read (with real error messages) happens if the user picks
        it, in import_bitbox_backup().
        """
        import bitbox_sd

        try:
            dir_names = Specter._read_sd(bitbox_sd.list_backup_dirs)
        except SpecterError:
            return None
        return dir_names or None

    async def import_mnemonic(self):
        buttons = [(host, host.button) for host in self.hosts if host.is_enabled]
        if self._bitbox_backup_dirs_or_none():
            buttons.append((self.BITBOX_BACKUP, "BitBox microSD backup"))
        host = await self.gui.menu(title="What to use for import?", note="\n",
            buttons=buttons,
            last=(255, None))
        if host == 255:
            return
        if host == self.BITBOX_BACKUP:
            return await self.import_bitbox_backup()
        # If the SD host was picked, warn once about device-encrypted
        # recovery phrases on the card that the active keystore can't see
        # (they don't match the import file filter). Deliberately scoped
        # to this import flow - not run on every SD file pick elsewhere
        # (PSBTs, descriptors), where the same hint would just be noise.
        # Only SDHost provides this method.
        warn = getattr(host, "warn_about_encrypted_files", None)
        if warn is not None:
            await warn()
        stream = await host.get_data()
        if not stream:
            return
        data = stream.read()
        # digital mnemonic
        if len(data) >= 4*12 and len(data) <= 4*24 and len(data) % 12 == 0 and (b" " not in data):
            mnemonic = " ".join([bip39.WORDLIST[int(data[4*i:4*i+4])] for i in range(len(data)//4)])
        # binary mnemonic
        elif len(data) >= 16 and len(data) <= 32:
            mnemonic = bip39.mnemonic_from_bytes(data)
        # text mnemonic
        else:
            mnemonic = data.decode()
            # split on \n and \r to avoid double-scan
            mnemonic = mnemonic.split("\r")[0].split("\n")[0]
            if not bip39.mnemonic_is_valid(mnemonic):
                raise SpecterError("Invalid data: %r" % mnemonic)
        return await self.confirm_and_set_mnemonic(mnemonic)

    async def confirm_and_set_mnemonic(self, mnemonic):
        """
        Shows the standard mnemonic confirmation screen and, if the user
        confirms, loads the mnemonic through the normal Specter key flow.

        This is the single tail shared by every source that produces a
        recovery phrase for the "Import recovery phrase" menu (host data
        via QR/SD/USB, and BitBox microSD backups). Once a source has a
        valid mnemonic string it must call this and nothing else - no
        caller may re-implement the confirmation, the set_mnemonic call, or
        any follow-up state change.

        Returns the next menu on success, or None if the user cancelled.
        """
        scr = MnemonicPrompt(title="Imported mnemonic:", mnemonic=mnemonic)
        # confirm mnemonic
        if not await self.gui.show_screen()(scr):
            return
        return self.set_mnemonic(mnemonic, "")

    def set_mnemonic(self, mnemonic, password=""):
        self.keystore.set_mnemonic(mnemonic.strip(), password)
        self.init_apps()
        self.current_menu = self.mainmenu
        return self.mainmenu

    @staticmethod
    def _split_backup_id(dir_name):
        """Full 64-character backup id, wrapped onto two lines - too wide
        for a single line pretty much anywhere in this UI."""
        half = len(dir_name) // 2
        return "%s\n%s" % (dir_name[:half], dir_name[half:])

    def _peek_backup_name(self, dir_name, mounted=False):
        """
        Best-effort read of just the `name` metadata field of one backup
        copy, so the selection menu (phase 2 of import_bitbox_backup, run
        before any copy has been checksum/id-verified) can show something
        more meaningful than the raw backup id.

        Deliberately uses parse_backup() (structural parse only) rather
        than the full validate_backup()/load_backup(): a cosmetic label
        doesn't need checksum or majority-vote resolution, and this must
        never reject a directory just because one copy happens to be
        damaged - that's still handled properly in phase 3.

        Never raises: any problem (unreadable card, corrupt/foreign file,
        no name set) just means no label is available, and the caller
        falls back to showing the id instead. Reads real backup file
        contents to get there - same read-only guarantee as the rest of
        this flow (nothing is ever written) - and zeroizes everything
        before returning, including the unused, unverified seed bytes
        that parse_backup() also returns.

        Pass mounted=True when the caller already holds the SD mount
        window (as _list_sdcard_items does): this must NOT open a second
        one via _read_sd(), because on real hardware os.mount() on an
        already-mounted path raises - which would silently turn every
        label here into the raw-id fallback. (Invisible in the simulator,
        where mount() is a no-op.)
        """
        import bitbox_backup
        import bitbox_sd

        try:
            if mounted:
                raw_files = bitbox_sd.read_backup_files(dir_name)
            else:
                raw_files = self._read_sd(lambda: bitbox_sd.read_backup_files(dir_name))
        except Exception:
            return None
        fields = None
        try:
            try:
                fields = bitbox_backup.parse_backup(raw_files[0])
            except Exception:
                return None
            name = fields.get("name") or ""
            return name if name else None
        finally:
            if fields is not None:
                bitbox_backup.zeroize(fields.get("seed"))
            for buf in raw_files:
                bitbox_backup.zeroize(buf)

    @staticmethod
    def _read_sd(fn):
        """Runs one synchronous, read-only SD-card operation with the card
        mounted for the shortest possible window, and returns its result.

        The card is deliberately never left mounted across a GUI await: the
        user may spend minutes on a confirmation screen or typing a
        passphrase, and the rest of Specter (see hosts/sd.py::get_data)
        follows the same mount -> read -> unmount-before-GUI pattern.
        """
        import bitbox_sd

        if not platform.sdcard.is_present:
            raise SpecterError("SD card is not inserted")
        try:
            platform.sdcard.mount()
        except Exception as e:
            raise SpecterError("Could not mount the SD card:\n\n%s" % e)
        try:
            return fn()
        except bitbox_sd.BitboxSdError as e:
            raise SpecterError("Could not read the SD card:\n\n%s" % e)
        finally:
            try:
                platform.sdcard.unmount()
            except Exception:
                # The card may have been pulled mid-read. We never write to
                # it, so there is nothing to lose here - and swallowing this
                # must not hide the real outcome of fn(), which either
                # returned or raised already.
                pass

    @staticmethod
    def _format_backup_timestamp(timestamp):
        if not timestamp:
            # Never show 1970-01-01 for this - a missing/zero timestamp
            # means "not recorded", not "recorded as the Unix epoch".
            # Specter-DIY itself always writes 0 here (see
            # RAMKeyStore._write_bitbox_backup): the device is airgapped
            # and has no RTC, so it has no real date to write and must
            # not fabricate one.
            return "unknown (no clock)"
        try:
            y, mo, d, h, mi, s = conv_time(timestamp)[:6]
            return "%04d-%02d-%02d %02d:%02d UTC" % (y, mo, d, h, mi)
        except Exception:
            # helpers.conv_time() should always succeed for a valid u32
            # timestamp, but never let a display-formatting problem turn
            # into an import failure - fall back to the raw value.
            return "%d (unix time, UTC)" % timestamp

    async def import_bitbox_backup(self):
        """
        Recovers a BIP-39 recovery phrase from a native, unencrypted
        BitBox02 microSD backup.

        This method's responsibility is strictly limited to the BitBox
        specific part: find the backup directory, read the three files
        read-only, decode the protobuf, verify the checksum and the backup
        id, resolve redundancy (including majority recovery), extract the
        BIP-39 entropy and turn it into a mnemonic. It then hands that
        mnemonic to confirm_and_set_mnemonic() - the same tail every other
        import source uses - and adds nothing of its own afterwards.

        Consequently there is deliberately no BitBox specific handling of
        BIP-39 passphrases, PIN, storage or app state: a passphrase can be
        applied later through Specter's normal existing passphrase menu,
        exactly as after any other recovery phrase import.

        Reads the SD card read-only and never writes, renames or deletes
        anything on it. On any abort or error the currently loaded key (if
        any) is left completely untouched.
        """
        import bitbox_backup
        import bitbox_sd

        proceed = await self.gui.show_screen()(
            Prompt(
                "BitBox microSD backup",
                "BitBox microSD backups are stored as plain, unencrypted "
                "data and are NOT authenticated against tampering.\n\n"
                "Anyone with access to this card can recover the wallet "
                "from it or replace it with a different wallet.\n\n"
                "This import does not need the BitBox device password - "
                "that password protects the BitBox's internal storage, "
                "not this SD card backup. The format checksum only detects "
                "accidental corruption; it does not prove the backup's "
                "origin.\n\n"
                "Compare the recovery phrase with an independent trusted "
                "backup before using this wallet.\n\n"
                "Continue?",
                warning="Not encrypted or authenticated!",
            )
        )
        if not proceed:
            return

        # Phase 1: discover backups. Card is mounted only for the listing.
        try:
            dir_names = self._read_sd(bitbox_sd.list_backup_dirs)
            if not dir_names:
                raise SpecterError(
                    "No BitBox microSD backup was found.\n\n"
                    "Backups live in a 'bitbox02' folder at the root of "
                    "the SD card."
                )
        except SpecterError as e:
            await self.gui.alert("BitBox import failed", "%s" % e)
            return

        # Phase 2: let the user choose, with the card already unmounted.
        # Prefer showing each backup's own name (peeked from one copy,
        # unverified - see _peek_backup_name) over its raw id, since the
        # id alone is not something a user can recognize their backup by.
        # All peeks are batched into a single mount window: doing them
        # individually would mount/unmount the card once per backup, which
        # is slow and does the same work N times. If the card is pulled
        # between phase 1 and phase 2, fall back to raw ids for all
        # entries - the actual read in phase 3 will report the real error.
        def _peek_all():
            return {
                name: self._peek_backup_name(name, mounted=True)
                for name in dir_names
            }

        try:
            peeked = self._read_sd(_peek_all)
        except SpecterError:
            peeked = {name: None for name in dir_names}
        buttons = [
            (name, peeked[name] or self._split_backup_id(name))
            for name in dir_names
        ]
        selected = await self.gui.menu(
            buttons, title="Select a BitBox backup", last=(255, None)
        )
        if selected == 255 or selected is None:
            return

        # Phase 3: read + fully validate, then unmount before any further GUI.
        raw_files = None
        parsed = None
        try:
            raw_files = self._read_sd(
                lambda: bitbox_sd.read_backup_files(selected)
            )
            try:
                parsed, valid_copies, used_majority = bitbox_backup.load_backup(
                    selected, raw_files
                )
            except bitbox_backup.BitboxBackupError as e:
                raise SpecterError(
                    "This BitBox backup failed its integrity checks:\n\n%s" % e
                )
            finally:
                # The raw file images are no longer needed once parsed; wipe
                # them before we start waiting on the user.
                for buf in raw_files:
                    bitbox_backup.zeroize(buf)
                raw_files = None

            # From here on the card is unmounted and `parsed` is the only
            # structure holding secret material.
            word_count = {16: 12, 24: 18, 32: 24}[parsed.seed_length]
            valid_copies_text = "%d of 3" % valid_copies
            if used_majority:
                valid_copies_text += " (recovered via majority vote)"
            info = (
                "Name: %s\n"
                "Created: %s\n"
                "Seed: %d words\n"
                "Generator: %s\n"
                "Backup ID: %s\n"
                "Valid copies (integrity only): %s\n"
                "Authenticity: NOT VERIFIED"
            ) % (
                parsed.name or "(none)",
                self._format_backup_timestamp(parsed.timestamp),
                word_count,
                parsed.generator or "(unknown)",
                self._split_backup_id(selected),
                valid_copies_text,
            )
            if used_majority:
                info += (
                    "\n\nAll individual backup copies were damaged.\n"
                    "The wallet was reconstructed using bitwise majority "
                    "recovery.\n"
                    "Verify the recovery phrase carefully."
                )
            info += (
                "\n\nThis backup is not authenticated against tampering.\n"
                "Compare the recovery phrase on the next screen with an "
                "independent trusted backup before using this wallet."
            )

            confirmed = await self.gui.show_screen()(
                Prompt(
                    "BitBox backup",
                    info,
                    confirm_text="I verified independently",
                    warning=(
                        "Majority recovery used!"
                        if used_majority
                        else "Not authenticated - verify independently"
                    ),
                )
            )
            if not confirmed:
                return

            # `mnemonic` is a Python str and therefore cannot be zeroized -
            # an unavoidable limitation shared with every other recovery
            # phrase path in Specter (see docs/security-model.md).
            mnemonic = parsed.mnemonic()

            # BitBox-specific responsibility ends here: from this point on
            # this is just a normal BIP-39 recovery phrase, handed to the
            # exact same flow every other import source uses.
            return await self.confirm_and_set_mnemonic(mnemonic)
        except SpecterError as e:
            await self.gui.alert("BitBox import failed", "%s" % e)
            return
        finally:
            if raw_files:
                for buf in raw_files:
                    bitbox_backup.zeroize(buf)
            if parsed is not None:
                parsed.zeroize()

    async def mainmenu(self):
        # interactive hosts are enabled later
        for host in self.hosts:
            if not host.button:
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
                if res not in [True, False, None]:
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
        buttons.append((2, "Enter passphrase"))
        if hasattr(self.keystore, "show_mnemonic"):
            buttons.append((3, "Show recovery phrase"))
        buttons.extend([(None, "Security"), (4, "Device settings")])  # delimiter
        buttons.extend([(None, "About"), (6, "About this device")])
        # wait for menu selection
        menuitem = await self.gui.menu(buttons, last=(255, None), note=self._firmware_note())

        # process the menu button:
        # back button
        if menuitem == 255:
            return self.mainmenu
        elif menuitem == 1:
            res = await self.keystore.storage_menu()
            # storage_menu returns True if app reinit is required
            if res:
                self.init_apps()
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
        elif menuitem == 6:
            await self.show_about()
        else:
            print(menuitem)
            raise SpecterError("Not implemented")
        return self.settingsmenu

    async def select_network(self):
        buttons = [
            (None, "Production"),
            ("main", "Bitcoin Mainnet"),
            ("liquidv1", "Liquid Mainnet"),
            (None, "Testnets"),
            ("test", "Testnet"),
            ("signet", "Signet"),
            ("regtest", "Regtest"),
            ("liquidtestnet", "Liquid Testnet"),
            ("elementsregtest", "Liquid Regtest"),
        ]
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

    async def show_about(self):
        await self.gui.alert(
            "About this device",
            self._firmware_note(include_details=True),
            button_text="Close",
        )

    async def communication_settings(self):
        buttons = [
            (None, "Communication channels")
        ] + [
            (host, host.settings_button)
            for host in self.hosts
            if host.settings_button is not None
        ]
        while True:
            menuitem = await self.gui.menu(buttons,
                                      title="Communication settings",
                                      note=self._firmware_note(),
                                      last=(255, None)
            )
            if menuitem == 255:
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

    @property
    def settings_fname(self):
        return self.SETTINGS_DIR+"/global.settings"

    def load_settings(self, fname=None):
        settings = {}
        try:
            if fname is None:
                fname = self.settings_fname
            adata, _ = self.keystore.load_aead(fname, key=self.keystore.settings_key)
            settings = json.loads(adata.decode())
        except Exception as e:
            print(e)
        return settings

    def save_settings(self, settings, fname=None):
        maybe_mkdir(self.SETTINGS_DIR)
        if fname is None:
            fname = self.settings_fname
        self.keystore.save_aead(fname,
                           adata=json.dumps(settings).encode(),
                           key=self.keystore.settings_key
        )

    async def experimental_settings(self):

        controls = [{
            "label": "Taproot",
            "hint": "Taproot support only for single-key wallets\nwithout tap script trees",
            "value": self.GLOBAL.get("experimental", {}).get("taproot", False)
        }]

        scr = HostSettings(
            controls,
            title="Experimental features",
            note="Experimental features are unstable,\n"
            "only enable them if you really want to try.\n"
            "Report developers in case of any issues.",
        )
        res = await self.gui.show_screen()(scr)
        if res is None:
            return
        taproot, *_ = res
        # for now only experimental, can be extended
        settings = {
            "experimental": {
                "taproot": taproot,
            }
        }
        self.GLOBAL = settings
        BaseApp.GLOBAL = settings
        self.save_settings(settings)

    async def update_devsettings(self):
        buttons = [
            (None, "Categories")
        ] + [
            (1, "Communication"),
            # (2, "Applications"),
            # (3, "Experimental"),
        ] + [
            (None, "Global settings"),
            (42, "About this device"),
        ]
        if hasattr(self.keystore, "lock"):
            buttons.extend([(777, "Change PIN code")])
        buttons += [
            (456, "Reboot"),
            (789, "SD card", platform.sdcard.is_present),
            (123, "Wipe the device", True, 0x951E2D),
        ]
        while True:
            menuitem = await self.gui.menu(buttons,
                                      title="Device settings",
                                      note=self._firmware_note(),
                                      last=(255, None)
            )
            if menuitem == 255:
                return
            elif menuitem == 3:
                await self.experimental_settings()
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
            elif menuitem == 789:
                await self.sdcard_menu()
                return
            elif menuitem == 777:
                await self.keystore.change_pin()
                return
            elif menuitem == 42:
                await self.show_about()
                return
            elif menuitem == 1:
                await self.communication_settings()
            else:
                print(menuitem)
                raise SpecterError("Not implemented")

    @property
    def fingerprint(self):
        return self.keystore.fingerprint

    def wipe(self):
        # TODO: wipe the smartcard as well?
        # platform.wipe
        wipe()

    def _list_sdcard_items(self):
        """
        Scans the SD card root for the Specter-related items this menu
        knows how to describe and securely delete: device-encrypted key
        files (from any device, not just this one - see hosts/sd.py's
        similar hint for why they matter even when unreadable here),
        plaintext recovery-phrase exports, and BitBox backup
        directories.

        Deliberately doesn't enumerate anything else that might be on
        the card (PSBTs, unrelated files) - "Format entire SD card" in
        _sdcard_delete_menu() is the tool for wiping everything
        indiscriminately.

        Returns a list of (kind, identifier, label) tuples. `identifier`
        is a full file path for "enc"/"plain" items, or a bare BitBox
        backup id for "bitbox" items (whose actual files live one level
        deeper, inside bitbox02/<id>/).
        """
        sdpath = platform.fpath("/sd")
        items = []
        platform.sdcard.mount()
        try:
            enumerated = 0
            for entry in os.ilistdir(sdpath):
                name, entry_type = entry[0], entry[1]
                if name in (".", ".."):
                    continue
                enumerated += 1
                if enumerated > self._SDCARD_LIST_MAX_ENTRIES:
                    break
                if entry_type != 0x8000:  # not a regular file
                    continue
                lname = name.lower()
                if lname.startswith(SD_FILE_PREFIX):
                    label = name.split(".", 1)[1] if "." in name else name
                    items.append(("enc", "%s/%s" % (sdpath, name), label))
                elif lname.endswith(".specter.txt"):
                    items.append(("plain", "%s/%s" % (sdpath, name), name[: -len(".specter.txt")]))
            try:
                import bitbox_sd
                for dir_name in bitbox_sd.list_backup_dirs():
                    # the card is already mounted here - a nested mount
                    # would fail on hardware, so peek within this window
                    label = self._peek_backup_name(dir_name, mounted=True) or dir_name
                    items.append(("bitbox", dir_name, label))
            except Exception:
                # no bitbox02/ directory, or it couldn't be listed - not
                # having any BitBox backups is not an error here.
                pass
        finally:
            platform.sdcard.unmount()
        return items

    @staticmethod
    def _sdcard_item_label(item):
        kind, _ident, label = item
        prefix = {"enc": "Encrypted: ", "plain": "Plaintext: ", "bitbox": "BitBox: "}[kind]
        return prefix + label

    async def sdcard_menu(self):
        """
        Entry point for managing what's stored on the SD card: shows how
        much Specter-related data is on it, and offers "Delete data" to
        either securely erase one item or format the whole card.
        """
        if not platform.sdcard.is_present:
            await self.gui.alert("No SD card", "There is no SD card inserted.")
            return
        while True:
            items = self._list_sdcard_items()
            note = (
                "%d Specter item(s) found on the card" % len(items)
                if items
                else "No Specter data found on the card"
            )
            menuitem = await self.gui.menu(
                [
                    (None, "SD card"),
                    ("delete", "Delete data", True, 0x951E2D),
                ],
                title="SD card",
                note=note,
                last=(255, None),
            )
            if menuitem == 255:
                return
            if menuitem == "delete":
                await self._sdcard_delete_menu(items)

    async def _sdcard_delete_menu(self, items):
        buttons = [(None, "What do you want to delete?")]
        for item in items:
            buttons.append((item, self._sdcard_item_label(item)))
        buttons.append(("format", "Format entire SD card", True, 0x951E2D))
        choice = await self.gui.menu(
            buttons, title="Delete data", last=(255, None)
        )
        if choice == 255 or choice is None:
            return
        if choice == "format":
            await self.format_sdcard()
            return
        await self._delete_sdcard_item(choice)

    async def _delete_sdcard_item(self, item):
        kind, ident, label = item
        kind_desc = {
            "enc": "an encrypted recovery phrase",
            "plain": "a plaintext recovery phrase",
            "bitbox": "a BitBox backup",
        }[kind]
        if not await self.gui.prompt(
            "Delete this item?",
            "\n\n%s\n\nThis is %s.\n\n"
            "It will be overwritten with fresh random data several "
            "times before being deleted - the same overwrite-then-"
            "delete principle BitBox itself uses for its own backups, "
            "just more thoroughly. Much harder to recover than a "
            "normal delete, though still not as thorough as formatting "
            "the whole card.\n\n"
            "Continue?" % (label, kind_desc),
        ):
            return
        platform.sdcard.mount()
        try:
            if kind == "bitbox":
                import bitbox_sd
                dir_path = "%s/%s/%s" % (
                    platform.fpath("/sd"), bitbox_sd.BITBOX_ROOT_DIRNAME, ident
                )
                platform.secure_delete_tree(dir_path)
            else:
                platform.secure_delete_file(ident)
        except Exception as e:
            await self.gui.alert("Delete failed", "%s" % e)
            return
        finally:
            platform.sdcard.unmount()
        await self.gui.alert("Deleted", "The item has been securely deleted.")

    async def format_sdcard(self):
        """
        Securely erases and reformats the SD card: every block is
        overwritten with random data (so recovering anything afterwards
        is far harder than after a normal delete) and a fresh, empty
        filesystem is created. Destroys everything on the card, not just
        files Specter-DIY created, and cannot be undone.
        """
        if not platform.sdcard.is_present:
            await self.gui.alert("No SD card", "There is no SD card inserted.")
            return
        if not await self.gui.prompt(
            "Format the SD card?",
            "\n\nThis erases EVERYTHING on the SD card - not just files "
            "Specter-DIY created, all of it - and cannot be undone.\n\n"
            "Every block is overwritten with random data before the "
            "card is reformatted, which makes recovering anything from "
            "it far harder than a normal delete.\n\n"
            "Note: SD cards manage their own wear leveling, so a small "
            "amount of old data could in theory still linger in space "
            "the card's own controller has set aside and never exposed "
            "to us. Software can't rule that out on any SD card - only "
            "destroying the card physically can.\n\n"
            "This can take a long time depending on the card's size and "
            "speed. Do not remove the card or power off the device "
            "while it's running.\n\n"
            "Are you sure?",
        ):
            return
        if not await self.gui.prompt(
            "Last chance",
            "\n\nThis cannot be undone.\n\nFormat the SD card now?",
        ):
            return

        scr = Progress(
            "Formatting SD card",
            "Overwriting and reformatting - please wait.\n"
            "Do not remove the card or power off the device.",
            button_text=None,
        )
        await self.gui.load_screen(scr)

        async def update_progress(fraction):
            scr.set_progress(fraction)
            scr.tick(5)

        try:
            await platform.sdcard.erase_and_format(progress_cb=update_progress)
        except Exception as e:
            await self.gui.alert("Format failed", "%s" % e)
            return
        await self.gui.alert(
            "Success!", "The SD card has been erased and reformatted."
        )

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
        settings = self.load_settings()
        self.GLOBAL = settings
        BaseApp.GLOBAL = settings

    async def maybe_import_mnemonic(self, stream, popup=False, show_fn=None):
        if show_fn is None:
            show_fn = self.gui.show_screen(popup)
        data = stream.read(240) # one word is at most 8 chars, so total len is < 240 even if it has prefix of some kind (for future)
        mnemonic_type = ""
        # digital mnemonic
        d = data.strip()
        if len(d) >= 4*12 and len(d) <= 4*24 and len(d) % 12 == 0 and (b" " not in d):
            mnemonic = " ".join([bip39.WORDLIST[int(d[4*i:4*i+4])] for i in range(len(d)//4)])
            mnemonic_type = "digital"
        # binary mnemonic
        elif len(data) >= 16 and len(data) <= 32:
            mnemonic = bip39.mnemonic_from_bytes(data)
            mnemonic_type = "binary"
        # text mnemonic
        else:
            mnemonic = data.decode()
            # split on \n and \r to avoid double-scan
            mnemonic = mnemonic.split("\r")[0].split("\n")[0]
            if not bip39.mnemonic_is_valid(mnemonic):
                raise SpecterError("Invalid data: %r" % mnemonic)
            mnemonic_type = "text"
        scr = MnemonicPrompt(title="Imported mnemonic:", mnemonic=mnemonic, note="Data looks like a %s mnemonic.\nDo you want to use it?" % mnemonic_type)
        # confirm mnemonic
        if not await show_fn(scr):
            return
        self.keystore.set_mnemonic(mnemonic, "")
        self.init_apps()

    async def process_host_request(self, stream, popup=True, appname=None, show_fn=None):
        """
        This method is called whenever we got data from the host.
        It tries to find a proper app and pass the stream with data to it.
        """
        self.gui.show_loader(title="Processing host data...")
        res = None
        if show_fn is None:
            show_fn = self.gui.show_screen(popup)
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
                stream.seek(0)
                try:
                    await self.maybe_import_mnemonic(stream, popup, show_fn)
                    return
                except Exception as e:
                    print(e)
                    raise HostError("Can't find matching app for this request:\n\n %r" % stream.read(100))
            # TODO: if more than one - ask which one to use
            if len(matching_apps) > 1:
                raise HostError(
                    "Not sure what app to use...\n\nThere are %d" % len(matching_apps)
                )
            stream.seek(0)
            app = matching_apps[0]
            res = await app.process_host_command(stream, show_fn)
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
