# Specter interaction script
from hwilib.hwwclient import HardwareWalletClient
from hwilib.errors import ActionCanceledError, BadArgumentError, DeviceBusyError, DeviceFailureError, UnavailableActionError, common_err_msgs, handle_errors
from hwilib.base58 import xpub_main_2_test
from hwilib import base58

import serial
import serial.tools.list_ports
import socket, time

# This class extends the HardwareWalletClient for Specter-specific things
class SpecterClient(HardwareWalletClient):
    """Actuall Specter HWI class"""
    def __init__(self, path, password='', expert=False):
        super().__init__(path, password, expert)
        self.simulator = (":" in path)
        if self.simulator:
            self.dev = SpecterSimulator(path)
        else:
            self.dev = SpecterUSBDevice(path)

    def query(self, data, timeout=None):
        res = self.dev.query(data, timeout)
        if res == "error: User cancelled":
            raise ActionCanceledError("User didn't confirm action")
        elif res.startswith("error: "):
            raise BadArgumentError(res[7:])
        return res

    def get_fingerprint(self):
        # this should be fast
        return self.query("fingerprint", timeout=0.1)

    def get_pubkey_at_path(self, path):
        """Returns a dict with xpub"""
        # this should be fast
        xpub = self.query("xpub %s" % path, timeout=0.1)
        # Specter returns xpub with a prefix 
        # for a network currently selected on the device
        if self.is_testnet:
            return {'xpub': xpub_main_2_test(xpub)}
        else:
            return {'xpub': xpub_test_2_main(xpub)}

    def sign_tx(self, tx):
        """Signs base64-encoded psbt transaction"""
        # this one can hang for quite some time
        signed_tx = self.query("sign %s" % tx.serialize())
        return {'psbt': signed_tx}

    # Must return a base64 encoded string with the signed message
    # The message can be any string. keypath is the bip 32 derivation path for the key to sign with
    def sign_message(self, message, keypath):
        sig = self.query('signmessage %s %s' % (keypath, message))
        return {"signature": sig}

    # Display address of specified type on the device. Only supports single-key based addresses.
    def display_address(self, keypath, p2sh_p2wpkh, bech32):
        if p2sh_p2wpkh:
            fmt = "sh-wpkh %s"
        elif bech32:
            fmt = "wpkh %s"
        else:
            fmt = "pkh %s"
        address = self.query("showaddr %s" % (fmt % keypath))
        return {'address': address}

    # Setup a new device
    def setup_device(self, label='', passphrase=''):
        raise UnavailableActionError('Specter does not support software setup')

    # Wipe this device
    def wipe_device(self):
        raise UnavailableActionError('Specter does not support wiping via software')

    # Restore device from mnemonic or xprv
    def restore_device(self, label=''):
        raise UnavailableActionError('Specter does not support restoring via software')

    # Begin backup process
    def backup_device(self, label='', passphrase=''):
        raise UnavailableActionError('Specter does not support backups')

    # Close the device
    def close(self):
        # nothing to do here - we close on every query
        pass

    # Prompt pin
    def prompt_pin(self):
        raise UnavailableActionError('Specter does not need a PIN sent from the host')

    # Send pin
    def send_pin(self, pin):
        raise UnavailableActionError('Specter does not need a PIN sent from the host')

def enumerate(password=''):
    """
    Returns a list of detected Specter devices 
    with their fingerprints and client's paths
    """
    results = []
    # find ports with micropython's VID
    ports = [port.device for port 
                         in serial.tools.list_ports.comports()
                         if is_micropython(port)]
    try:
        # check if there is a simulator on port 8789
        # and we can connect to it
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 8789))
        s.close()
        ports.append("127.0.0.1:8789")
    except:
        pass

    for port in ports:
        # for every port try to get a fingerprint
        try:
            path = port
            data = {
                'type': 'specter',
                'model': 'specter-diy',
                'path': path,
                'needs_passphrase': False
            }
            client = SpecterClient(path)
            data['fingerprint'] = client.get_fingerprint()
            client.close()
            results.append(data)
        except:
            pass
    return results

############# Helper functions and base classes ##############

def xpub_test_2_main(xpub: str) -> str:
    data = base58.decode(xpub)
    main_data = b'\x04\x88\xb2\x1e' + data[4:-4]
    checksum = base58.hash256(main_data)[0:4]
    return base58.encode(main_data + checksum)

def is_micropython(port):
    return "VID:PID=F055:" in port.hwid.upper()

class SpecterBase:
    """Class with common constants and command encoding"""
    EOL = b"\r\n"
    ACK = b"ACK"
    def prepare_cmd(self, data):
        """
        Prepends command with 2*EOL and appends EOL at the end.
        Double EOL in the beginning makes sure all pending data
        will be cleaned up.
        """
        return self.EOL*2 + data.encode('utf-8') + self.EOL

class SpecterUSBDevice(SpecterBase):
    """
    Base class for USB device.
    Implements a simple query command over serial
    """
    def __init__(self, path):
        self.ser = serial.Serial(baudrate=115200, timeout=30)
        self.ser.port = path

    def query(self, data, timeout=None):
        self.ser.timeout=timeout
        self.ser.open()
        self.ser.write(self.prepare_cmd(data))
        # first we should get ACK
        res = self.ser.read_until(self.EOL)[:-len(self.EOL)]
        # then we should get the data itself
        if res == self.ACK:
            res = self.ser.read_until(self.EOL)[:-len(self.EOL)]
        self.ser.close()
        return res.decode()

class SpecterSimulator(SpecterBase):
    """
    Base class for the simulator.
    Implements a simple query command over tcp/ip socket
    """
    def __init__(self, path):
        arr = path.split(":")
        self.sock_settings = (arr[0], int(arr[1]))

    def read_until(self, s, eol, timeout=None):
        t0 = time.time()
        res = b""
        while not (eol in res):
            try:
                raw = s.recv(1)
                res += raw
            except Exception as e:
                time.sleep(0.01)
            if timeout is not None and time.time() > t0+timeout:
                s.close()
                raise DeviceBusyError("Timeout")
        return res

    def query(self, data, timeout=None):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(self.sock_settings)
        s.send(self.prepare_cmd(data))
        s.setblocking(False)
        res = self.read_until(s, self.EOL, 0.1)[:-len(self.EOL)]
        if res == self.ACK:
            res = self.read_until(s, self.EOL, timeout)[:-len(self.EOL)]
        s.close()
        return res.decode()
