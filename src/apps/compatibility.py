"""
This app parses data in various format that are not native to Specter
and converts to commands that Specter will understand.
After processing it sends converted command to a corresponding app.
"""
from app import BaseApp, AppError
from io import BytesIO
import json

class App(BaseApp):
    name = "compatibility"
    prefixes = []

    def can_process(self, stream):
        """Detects if it can process the stream"""
        c = stream.read(64)
        # rewind
        stream.seek(-len(c), 1)
        # check if it's a json
        if c.startswith(b"{"):
            return True
        return False

    async def process_host_command(self, stream, show_fn):
        # check if we've got filename, not a stream:
        if isinstance(stream, str):
            with open(stream, "rb") as f:
                obj = json.load(f)
        else:
            obj = json.load(stream)
        if "descriptor" in obj:
            # this is wallet export json (Specter Desktop, FullyNoded and others)
            return await self.parse_software_wallet_json(obj, show_fn)
        raise AppError("Failed parsing data")

    async def parse_software_wallet_json(self, obj, show_fn):
        if "descriptor" not in obj:
            raise AppError("Invalid wallet json")
        # get descriptor without checksum
        desc = obj["descriptor"].split("#")[0]
        # replace /0/* to /{0,1}/* to add change descriptor
        desc = desc.replace("/0/*", "/{0,1}/*")
        label = obj.get("label", "Imported wallet")
        s, _ = await self.communicate(BytesIO(b"listwallets"), app="wallets")
        names = json.load(s)
        suggestion = label
        i = 0
        while suggestion in names:
            suggestion = "%s (%d)" % (label, i)
            i += 1
        data = "addwallet %s&%s" % (suggestion, desc)
        stream = BytesIO(data.encode())
        return await self.communicate(stream, app="wallets", show_fn=show_fn)
