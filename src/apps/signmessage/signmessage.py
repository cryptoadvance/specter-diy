"""
Demo of a simple app that extends Specter with custom functionality.
"""
from app import BaseApp, AppError

from bitcoin import ec, bip32
from hashlib import sha256
from binascii import b2a_base64, unhexlify
import secp256k1
from io import BytesIO

class MessageApp(BaseApp):
    """
    This app can sign a text message with a private key.
    """
    prefixes = [b"signmessage"]
    async def process_host_command(self, prefix, stream, gui, popup):
        """
        If command with one of the prefixes is received
        it will be passed to this method.
        Should return a stream (file, BytesIO etc).
        """
        if prefix != b"signmessage":
            # WTF? It's not our data...
            raise AppError("Prefix is not valid: %s" % prefix.decode())
        # data format: derivation_path<space>message to sign
        # read all and delete all crap at the end (if any)
        # also message should be utf-8 decodable
        data = stream.read().strip().decode()
        if " " not in data:
            raise AppError("Invalid data encoding")
        arr = data.split(" ")
        derivation_path = arr[-1]
        message = " ".join(arr[:-1])
        # if we have fingerprint
        if not derivation_path.startswith("m/"):
            fingerprint = unhexlify(derivation_path[:8])
            if fingerprint != self.keystore.fingerprint:
                raise AppError("Not my fingerprint")
            derivation_path = "m"+derivation_path[8:]
        derivation_path = bip32.parse_path(derivation_path)
        # ask the user if he really wants to sign this message
        res = await gui.prompt("Sign message with private key at %s?" % bip32.path_to_str(derivation_path), "Message:\n%s" % message, popup=popup)
        if res is False:
            return None
        sig = self.sign_message(derivation_path, message.encode())
        return BytesIO(sig)

    def sign_message(self, derivation, msg:bytes, compressed:bool=True) -> bytes:
        """Sign message with private key"""
        msghash = sha256(
                        sha256(
                            b'\x18Bitcoin Signed Message:\n' + bytes([len(msg)]) + msg
                        ).digest()
                    ).digest()
        sig, flag = self.keystore.sign_recoverable(derivation, msghash)
        c = 4 if compressed else 0
        flag = bytes([27+flag+c])
        ser = flag + secp256k1.ecdsa_signature_serialize_compact(sig._sig)
        return b2a_base64(ser).strip().decode()

