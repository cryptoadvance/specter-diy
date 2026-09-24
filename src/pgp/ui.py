import sys
import os
import hashlib
from binascii import hexlify
import asyncio

import platform
from gui.screens.advancedalert import AdvancedAlert
from gui.screens.prompt import Prompt
from gui.screens.menu import Menu
from gui.common import add_label, styles
from gui.core import update
from helpers import conv_time
from .base import (
    MAX_SD_LIST_FILES,
    UNSUPPORTED_KEY_MSG,
    PGPBinaryError,
    PGPError,
    PGPInvalidKeyError,
    PGPKeyTooLargeError,
    PGPUnsupportedKeyError,
    basename,
    companion_filename,
    iter_file_chunks,
)
from .checksums import (
    KIND_BINARY,
    KIND_CHECKSUM_FILES,
    KIND_EMPTY,
    KIND_LONG_CHECKSUM_FILES,
    KIND_LONG_TEXT,
    KIND_TEXT,
    unverified_files,
    verify_checksum_files,
)
from .codec import format_fingerprint, looks_like_public_key
from .pgp import load_ascii_armored_public_key, verify_signed_checksums
import lvgl as lv

PAYLOAD_KINDS = {
    KIND_BINARY: "Payload is binary or non-ascii",
    KIND_LONG_TEXT: "Payload is too long to be displayed",
    KIND_LONG_CHECKSUM_FILES: "Checksum list is too long to display",
    KIND_EMPTY: "Signed payload is empty.",
}

SD_MISSING_MSG = "SD card is not present"
SD_TOO_MANY_FILES_MSG = "Too many files on the SD card."


class PGPVerification:
    async def pgp_verification(self):
        try:
            await self._pgp_verification()
        finally:
            self.pgp_fingerprint = None
            self.pgp_signing_keys = []
            self.pgp_key_file = None
            self.pgp_expires_at = None

    def _pgp_on_sd(self, fn):
        if not platform.sdcard.is_present:
            raise PGPError(SD_MISSING_MSG)
        platform.sdcard.mount()
        try:
            return fn()
        finally:
            platform.sdcard.unmount()

    async def _pgp_verification(self):
        while True:
            try:
                fname = await self._pgp_select_sd_file(
                    title="PGP verification",
                    subtitle="Step 1: Load PGP key",
                    extensions=(".asc", ".pgp", ".gpg", ".key"),
                )
            except PGPError as e:
                await self._pgp_error_alert(str(e))
                return
            if fname is None or fname == 255:
                return
            try:
                def load():
                    return load_ascii_armored_public_key(iter_file_chunks(fname))

                fingerprint, signing_keys, expires_at = self._pgp_on_sd(load)
            except PGPBinaryError:
                await self._pgp_invalid_key_alert(binary=True)
                continue
            except PGPUnsupportedKeyError:
                await self._pgp_unsupported_key_alert()
                continue
            except (PGPKeyTooLargeError, PGPInvalidKeyError) as e:
                await self._pgp_error_alert(str(e))
                continue
            except PGPError as e:
                if str(e) == SD_MISSING_MSG:
                    await self._pgp_error_alert(str(e))
                    return
                await self._pgp_invalid_key_alert()
                continue
            except Exception:
                await self._pgp_invalid_key_alert()
                continue
            self.pgp_fingerprint = fingerprint
            self.pgp_signing_keys = signing_keys
            self.pgp_key_file = fname
            self.pgp_expires_at = expires_at
            while True:
                if not await self._pgp_confirm_fingerprint(fingerprint, expires_at):
                    break
                if await self._pgp_verify_signature_flow():
                    return

    async def _pgp_select_sd_file(
        self, title: str, subtitle: str, extensions, exclude=None, skip_public_keys: bool = False
    ):
        buttons = [(None, "SD card")]
        sdpath, files = self._pgp_list_sd_files(
            extensions, skip_public_keys=skip_public_keys
        )
        exclude = exclude or []
        for name in files:
            path = sdpath + "/" + name
            if path in exclude or name in exclude:
                continue
            display = name if len(name) <= 33 else name[:18] + "..." + name[-12:]
            buttons.append((path, display))
        return await self.gui.menu(
            buttons=buttons,
            title=title,
            subtitle=subtitle,
            last=(255, None),
        )

    def _pgp_list_sd_files(self, extensions=None, skip_public_keys: bool = False) -> tuple:
        if not platform.sdcard.is_present:
            raise PGPError(SD_MISSING_MSG)
        sdpath = platform.fpath("/sd")
        files = []
        platform.sdcard.mount()
        try:
            for entry in os.ilistdir(sdpath):
                name = entry[0]
                if name in (".", "..") or entry[1] != 0x8000:
                    continue
                if not self._pgp_name_matches(name, extensions):
                    continue
                if skip_public_keys and self._pgp_head_is_public_key(
                    sdpath + "/" + name
                ):
                    continue
                if len(files) >= MAX_SD_LIST_FILES:
                    raise PGPError(SD_TOO_MANY_FILES_MSG)
                files.append(name)
        finally:
            platform.sdcard.unmount()
        files.sort()
        return sdpath, files

    def _pgp_head_is_public_key(self, path: str) -> bool:
        try:
            with open(path, "rb") as f:
                data = f.read(80)
        except Exception:
            return False
        return looks_like_public_key(data)

    def _pgp_name_matches(self, name: str, extensions) -> bool:
        if extensions is None:
            return True
        lower = name.lower()
        for ext in extensions:
            if lower.endswith(ext):
                return True
        return False

    async def _pgp_unsupported_key_alert(self):
        scr = AdvancedAlert(
            title="PGP verification",
            messages=[(UNSUPPORTED_KEY_MSG, "warning")],
        )
        await self.gui.show_screen()(scr)

    async def _pgp_invalid_key_alert(self, binary: bool = False):
        subtitle = "Invalid or unsupported ASCII-armored OpenPGP public key"
        if binary:
            subtitle += "\nBinary keys are not supported."
        await self._pgp_error_alert(subtitle)

    async def _pgp_error_alert(self, subtitle: str):
        menu = Menu(
            buttons=[],
            title="PGP verification",
            subtitle=subtitle,
            last=(255, None),
        )
        menu.subtitle.set_style(0, styles["warning"])
        await self.gui.load_screen(menu)
        await menu.result()

    async def _pgp_show_processing(self):
        menu = Menu(
            buttons=[],
            title="PGP verification",
            subtitle="Processing...",
        )
        await self.gui.load_screen(menu)
        update()
        update()
        await asyncio.sleep_ms(30)

    async def _pgp_verify_signature_flow(self):
        while True:
            try:
                fname = await self._pgp_select_sd_file(
                    title="PGP verification",
                    subtitle="Step 3: Verify signature & checksums",
                    extensions=(".asc", ".sig", ".txt"),
                    exclude=[self.pgp_key_file] if self.pgp_key_file else None,
                    skip_public_keys=True,
                )
            except PGPError as e:
                await self._pgp_error_alert(str(e))
                return False
            if fname is None or fname == 255:
                return False
            try:
                await self._pgp_show_processing()
                await self._pgp_verify_selected_signature(fname)
                return True
            except PGPError as e:
                await self._pgp_error_alert(str(e))
            except Exception as e:
                sys.print_exception(e)
                await self._pgp_error_alert("Invalid PGP signature.")

    async def _pgp_verify_selected_signature(self, fname: str):
        companion = companion_filename(fname)
        sdpath = platform.fpath("/sd")
        companion_path = sdpath + "/" + companion
        _, all_files = self._pgp_list_sd_files()
        if companion not in all_files:
            companion_path = None

        def verify():
            companion_factory = None
            if companion_path is not None:
                companion_factory = lambda: iter_file_chunks(companion_path)
            return verify_signed_checksums(
                self.pgp_signing_keys,
                lambda: iter_file_chunks(fname),
                companion_factory,
                fname,
            )

        kind, value = self._pgp_on_sd(verify)
        if kind != KIND_CHECKSUM_FILES:
            await self._pgp_show_signed_payload(kind, value)
            return
        verified, missing, corrupt, extras = self._pgp_check_checksum_files(
            value,
            all_files,
            [
                basename(self.pgp_key_file or ""),
                basename(fname),
                companion,
            ],
        )
        await self._pgp_show_checksum_results(verified, missing, corrupt, extras)

    def _pgp_check_checksum_files(self, entries: list, all_files: list, exclude_names: list) -> tuple:
        sdpath = platform.fpath("/sd")

        def sha256_of(name):
            try:
                h = hashlib.sha256()
                for chunk in iter_file_chunks(sdpath + "/" + name):
                    h.update(chunk)
                return hexlify(h.digest()).decode().lower()
            except Exception:
                return None

        def run():
            return verify_checksum_files(entries, sha256_of)

        verified, missing, corrupt = self._pgp_on_sd(run)
        listed = [name for _digest, name in entries]
        extras = unverified_files(all_files, listed, exclude_names)
        return verified, missing, corrupt, extras

    async def _pgp_show_checksum_results(
        self, verified: list, missing: list, corrupt: list, extras: list
    ):
        messages = []
        if corrupt:
            messages.append(
                (
                    "Some files contain different content than expected.",
                    "warning",
                )
            )
        parts = ["Verified files:"]
        if verified:
            parts.extend(verified)
        else:
            parts.append("No verified files")
        parts.append("")
        parts.append("Missing files:")
        if missing:
            parts.extend(missing)
        else:
            parts.append("No missing files")
        messages.append(("\n".join(parts), None))
        if corrupt:
            messages.append(
                ("Corrupted files:\n" + "\n".join(corrupt), "warning")
            )
        if extras:
            messages.append(
                ("Other files in this folder have not been verified.", None)
            )
        scr = AdvancedAlert(
            title="PGP verification",
            subtitle="Summary",
            messages=messages,
        )
        await self.gui.show_screen()(scr)

    async def _pgp_show_signed_payload(self, kind: str, value):
        subtitle = "Verified payload (could not parse as a checksums file):"
        use_mono = False
        if kind == KIND_TEXT:
            message = value
            use_mono = True
        else:
            # Fallback should never happen; classifier only returns known kinds.
            message = PAYLOAD_KINDS.get(kind, "Unsupported payload format")
        scr = AdvancedAlert(
            title="PGP verification",
            subtitle=subtitle,
            messages=[(message, None)],
        )
        if use_mono:
            style = lv.style_t()
            lv.style_copy(style, scr.labels[0].get_style(0))
            style.text.font = lv.font_roboto_mono_22
            scr.labels[0].set_style(0, style)
        await self.gui.show_screen()(scr)

    async def _pgp_confirm_fingerprint(self, fingerprint: bytes, expires_at=None):
        scr = Prompt(
            title="PGP verification",
            subtitle="Step 2: Verify fingerprint",
            message=format_fingerprint(fingerprint),
            confirm_text="Verified",
            cancel_text=lv.SYMBOL.LEFT + " Back",
        )
        style = lv.style_t()
        lv.style_copy(style, scr.message.get_style(0))
        style.text.font = lv.font_roboto_mono_22
        scr.message.set_style(0, style)
        instr = add_label(
            "Please verify this fingerprint against a trusted source.",
            scr=scr.page,
        )
        instr.align(scr.message, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
        if expires_at is not None:
            t = conv_time(expires_at)
            date = "%04d-%02d-%02d" % (t[0], t[1], t[2])
            lbl = add_label(
                "Expires on %s UTC.\n"
                "Don't trust this key after this date. We do not verify the signatures' creation date." % date,
                scr=scr.page,
                style="warning",
            )
            lbl.align(instr, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
        return await self.gui.show_screen()(scr)
