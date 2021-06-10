"""
Demo of a single-file app extending Specter functionality.
This app allows to set a label for the device.
"""
from app import BaseApp, AppError
from gui.screens import Prompt
from io import BytesIO

# Should be called App if you use a single file


class App(BaseApp):
    """Allows to set a label for the device."""
    name = "label"
    prefixes = [b"getlabel", b"setlabel"]

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
        if prefix == b"getlabel":
            label = self.get_label()
            obj = {"title": "Device's label is: %s" % label}
            stream = BytesIO(label.encode())
            return stream, obj
        elif prefix == b"setlabel":
            label = stream.read().strip().decode("ascii")
            if not label:
                raise AppError("Device label cannot be empty")
            scr = Prompt(
                "\n\nSet device label to: %s\n" % label,
                "Current device label: %s" % self.get_label(),
            )
            res = await show_screen(scr)
            if res is False:
                return None
            self.set_label(label)
            obj = {"title": "New device label: %s" % label}
            return BytesIO(label.encode()), obj
        else:
            raise AppError("Invalid command")

    def get_label(self):
        try:
            with open(self.path + "/label") as f:
                label = f.read()
            return label
        except Exception:
            return "Specter-DIY"

    def set_label(self, label):
        try:
            with open(self.path + "/label", "w") as f:
                f.write(label)
        except Exception:
            return AppError("Failed to save new label")
