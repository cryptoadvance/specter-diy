"""
This app parses data in various format that are not native to Specter
and converts to commands that Specter will understand.
After processing it sends converted command to a corresponding app.
"""
from app import BaseApp, AppError
from io import BytesIO
import json
from helpers import read_until
from embit import bip32
from binascii import unhexlify

CC_TYPES = {"BIP45": "sh", "P2WSH-P2SH": "sh-wsh", "P2WSH": "wsh"}

# functions that are app-agnostic, helps to test parsing
def parse_software_wallet_json(obj):
    """Parse software export json"""
    if "descriptor" not in obj:
        raise AppError("Invalid wallet json")
    # get descriptor without checksum
    desc = obj["descriptor"].split("#")[0]
    # replace /0/* to /{0,1}/* to add change descriptor
    desc = desc.replace("/0/*", "/{0,1}/*")
    label = obj.get("label", "Imported wallet")
    return label, desc


def parse_cc_wallet_txt(stream):
    """Parse coldcard wallet format"""
    name = "Imported wallet"
    script_type = None
    sigs_required = None
    global_derivation = None
    sigs_total = None
    cosigners = []
    current_derivation = None
    # cycle until we read everything
    char = b"\n"
    while char is not None:
        line, char = read_until(stream, b"\r\n", max_len=300)
        # skip comments
        while char is not None and (line.startswith(b"#") or len(line.strip()) == 0):
            # BW comment on derivation
            if line.startswith(b"# derivation:"):
                current_derivation = bip32.parse_path(line.split(b":")[1].decode().strip())
            line, char = read_until(stream, b"\r\n", max_len=300)
        if b":" not in line:
            continue
        arr = line.split(b":")
        if len(arr) > 2:
            raise AppError("Invalid file format")
        k, v = [a.strip().decode() for a in arr]
        if k == "Name":
            name = v
        elif k == "Policy":
            nums = [int(num) for num in v.split(" of ")]
            assert len(nums) == 2
            m, n = nums
            assert m > 0 and n >= m
            sigs_required = m
            sigs_total = n
        elif k == "Format":
            assert v in CC_TYPES
            script_type = CC_TYPES[v]
        elif k == "Derivation":
            der = bip32.parse_path(v)
            if len(cosigners) == 0:
                global_derivation = der
            else:
                current_derivation = der
        # fingerprint
        elif len(k) == 8:
            cosigners.append((unhexlify(k), current_derivation or global_derivation, bip32.HDKey.from_string(v)))
            current_derivation = None
    assert None not in [global_derivation, sigs_total, sigs_required, script_type, name]
    assert len(cosigners) == sigs_total
    xpubs = ["[%s]%s/{0,1}/*" % (bip32.path_to_str(der, fingerprint=fgp), xpub) for fgp, der, xpub in cosigners]
    desc = "sortedmulti(%d,%s)" % (sigs_required, ",".join(xpubs))
    for sc in reversed(script_type.split("-")):
        desc = "%s(%s)" % (sc, desc)
    return name, desc


class App(BaseApp):
    name = "compatibility"
    prefixes = []

    def can_process(self, stream):
        """Detects if it can process the stream"""
        c = stream.read(16)
        # rewind
        stream.seek(-len(c), 1)
        # check if it's a json
        if c.startswith(b"{"):
            return True
        # looks like coldcard wallet format
        if c.startswith(b"#") or c.startswith(b"Name:"):
            return True
        return False

    async def process_host_command(self, stream, show_fn):
        # check if we've got filename, not a stream:
        if isinstance(stream, str):
            with open(stream, "rb") as f:
                return await self.process_host_command(f, show_fn)
        # processing stream now
        c = stream.read(16)
        # rewind
        stream.seek(-len(c), 1)
        if c.startswith(b"{"):
            obj = json.load(stream)
            if "descriptor" in obj:
                # this is wallet export json (Specter Desktop, FullyNoded and others)
                return await self.parse_software_wallet_json(obj, show_fn)
        elif c.startswith(b"#") or c.startswith(b"Name:"):
            return await self.parse_cc_wallet_txt(stream, show_fn)
        raise AppError("Failed parsing data")

    async def get_wallet_name_suggestion(self, label):
        s, _ = await self.communicate(BytesIO(b"listwallets"), app="wallets")
        names = json.load(s)
        suggestion = label
        i = 0
        while suggestion in names:
            suggestion = "%s (%d)" % (label, i)
            i += 1
        return suggestion

    async def parse_software_wallet_json(self, obj, show_fn):
        label, desc = parse_software_wallet_json(obj)
        label = await self.get_wallet_name_suggestion(label)
        data = "addwallet %s&%s" % (label, desc)
        stream = BytesIO(data.encode())
        return await self.communicate(stream, app="wallets", show_fn=show_fn)

    async def parse_cc_wallet_txt(self, stream, show_fn):
        label, desc = parse_cc_wallet_txt(stream)
        label = await self.get_wallet_name_suggestion(label)
        data = "addwallet %s&%s" % (label, desc)
        stream = BytesIO(data.encode())
        return await self.communicate(stream, app="wallets", show_fn=show_fn)
