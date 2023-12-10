"""
Demo of a simple app that extends Specter with custom functionality.
"""
from app import BaseApp, AppError
from gui.screens import Prompt

from embit import ec, bip32, script, compact
from embit.liquid.networks import NETWORKS
from hashlib import sha256
from binascii import b2a_base64, unhexlify, a2b_base64, hexlify
import secp256k1
from io import BytesIO


class MessageApp(BaseApp):
    """
    This app can sign a text message with a private key.
    """

    prefixes = [b"signmessage"]
    name = "message"

    async def process_host_command(self, stream, show_screen):
        """
        If command with one of the prefixes is received
        it will be passed to this method.
        Should return a tuple:
        - stream (file, BytesIO etc)
        - meta object with title and note
        """
        # reads prefix from the stream (until first space)
        prefix = self.get_prefix(stream)
        if prefix != b"signmessage":
            # WTF? It's not our data...
            raise AppError("Prefix is not valid: %s" % prefix.decode())
        # data format: message to sign<space>derivation_path
        # read all and delete all crap at the end (if any)
        # also message should be utf-8 decodable
        data = stream.read().strip()
        if b" " not in data:
            raise AppError("Invalid data encoding")
        arr = data.split(b" ")
        derivation_path = arr[0].decode()
        message = b" ".join(arr[1:])
        # if we have fingerprint
        if not derivation_path.startswith("m"):
            fingerprint = unhexlify(derivation_path[:8])
            if fingerprint != self.keystore.fingerprint:
                raise AppError("Not my fingerprint")
            derivation_path = "m" + derivation_path[8:]
        # Returns a list of indexes
        derivation_path = bip32.parse_path(derivation_path)

        if message.startswith(b"ascii:"):
            message = message[len(b"ascii:") :]
        elif message.startswith(b"base64:"):
            message = a2b_base64(message[len(b"base64:") :])
        else:
            raise AppError("Invalid message encoding!")
        # try to decode with ascii characters
        try:
            msg = "Message:\n\n"
            msg += "__________________________________\n"
            msg += message.decode("ascii")
            msg += "\n__________________________________"
            # ask the user if he really wants to sign this message
        except:
            msg = "Hex message:\n\n%s" % hexlify(message).decode()
        scr = Prompt(
            "Sign message with private key at %s?" % bip32.path_to_str(derivation_path),
            msg,
        )
        res = await show_screen(scr)
        if res is False:
            return False
        sig = self.sign_message(derivation_path, message)
        # for GUI we can also return an object with helpful data
        pub = self.keystore.get_xpub(derivation_path).get_public_key()
        # default - legacy
        addr = script.p2pkh(pub).address(NETWORKS[self.network])
        if len(derivation_path) > 0:
            if derivation_path[0] == (0x80000000 + 84):
                addr = script.p2wpkh(pub).address(NETWORKS[self.network])
            if derivation_path[0] == (0x80000000 + 49):
                addr = script.p2sh(script.p2wpkh(pub)).address(NETWORKS[self.network])
        note = "Address: %s" % addr
        note += "\nDerivation path: %s" % bip32.path_to_str(derivation_path)
        obj = {
            "title": "Message signature:",
            "note": note,   
        }
        return BytesIO(sig), obj

    def sign_message(self, derivation, msg: bytes, compressed: bool = True) -> bytes:
        """Sign message with private key"""
        msghash = sha256(
            sha256(
                b"\x18Bitcoin Signed Message:\n" + compact.to_bytes(len(msg)) + msg
            ).digest()
        ).digest()
        sig, flag = self.keystore.sign_recoverable(derivation, msghash)
        c = 4 if compressed else 0
        flag = bytes([27 + flag + c])
        ser = flag + secp256k1.ecdsa_signature_serialize_compact(sig._sig)
        return b2a_base64(ser).strip().decode()
