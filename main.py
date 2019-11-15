import gui
from gui import screens, popups
from gui.decorators import queued
import gui.common

import urandom, os
import ujson as json
from ubinascii import hexlify, unhexlify

from bitcoin import ec, hashes, bip39, bip32
from bitcoin.networks import NETWORKS
from keystore import KeyStore

from qrscanner import QRScanner

qr_scanner = QRScanner()

# entropy that will be converted to mnemonic
entropy = None
# network we are using
network = None
# our key storage
keystore = KeyStore()

# detect if it's a hardware device or linuxport
try:
    import pyb
    simulator = False
except:
    simulator = True

# path to store #reckless entropy
if simulator:
    reckless_fname = "reckless.json"
else:
    reckless_fname = "/flash/reckless.json"

DEFAULT_XPUBS = []

def cancel_scan():
    print("Cancel scan!")
    qr_scanner.stop()
    show_main()

def wallets_menu():
    pass

def show_xpub(name, derivation):
    xpub = keystore.get_xpub(derivation).to_base58()
    fingerprint = hexlify(keystore.fingerprint).decode('utf-8')
    prefix = "[%s%s]" % (fingerprint, derivation[1:])
    popups.show_xpub(name, xpub, prefix=prefix)

def xpubs_menu():
    def selector(name, derivation):
        def cb():
            show_xpub(name, derivation)
        return cb
    buttons = []
    for name, derivation in DEFAULT_XPUBS:
        buttons.append((name, selector(name, derivation)))
    # buttons.append(("Back to Main menu", show_main))
    gui.create_menu(buttons=buttons, cb_back=show_main)

def scan_transaction():
    pass

def scan_address():
    pass

def set_default_xpubs(net):
    while len(DEFAULT_XPUBS) > 0:
        DEFAULT_XPUBS.pop()
    DEFAULT_XPUBS.append(("Single key", "m/84h/%dh/0h" % network["bip32"]))
    DEFAULT_XPUBS.append(("Miltisig", "m/48h/%dh/0h/2h" % network["bip32"]))

def select_network(name):
    global network
    if name in NETWORKS:
        network = NETWORKS[name]
        if keystore.is_initialized:
            set_default_xpubs(network)
            # load existing wallets for this network
            keystore.load_wallets(name)
            # create a default wallet if it doesn't exist
            if len(keystore.wallets) == 0:
                # create a wallet descriptor
                # this is not exactly compatible with Bitcoin Core though.
                # '_' means 0/* or 1/* - standard receive and change 
                #                        derivation patterns
                derivation = DEFAULT_XPUBS[0][1]
                xpub = keystore.get_xpub(derivation).to_base58()
                fingerprint = hexlify(keystore.fingerprint).decode('utf-8')
                prefix = "[%s%s]" % (fingerprint, derivation[1:])
                descriptor = "wpkh(%s%s/_)" % (prefix, xpub)
                keystore.create_wallet("Default", descriptor)
    else:
        raise RuntimeError("Unknown network")

def network_menu():
    def selector(name):
        def cb():
            try:
                select_network(name)
                show_main()
            except Exception as e:
                print(e)
                gui.error("%r" % e)
        return cb
    # could be done with iterator
    # but order is unknown then
    gui.create_menu(buttons=[
        ("Mainnet", selector("main")),
        ("Testnet", selector("test")),
        ("Regtest", selector("regtest")),
        ("Signet", selector("signet"))
    ])


def show_mnemonic():
    # print(bip39.mnemonic_from_bytes(entropy))
    popups.show_mnemonic(bip39.mnemonic_from_bytes(entropy))


def save_entropy():
    with open(reckless_fname, "w") as f:
        f.write('{"entropy":"%s"}' % hexlify(entropy).decode('utf-8'))
    with open(reckless_fname, "r") as f:
        d = json.loads(f.read())
    if "entropy" in d  and d["entropy"] == hexlify(entropy).decode('utf-8'):
        gui.alert("Success!", "Your key is saved in the memory now")
    else:
        gui.error("Something went wrong")

def delete_entropy():
    try:
        os.remove(reckless_fname)
        gui.alert("Success!", "Your key is deleted")
    except:
        gui.error("Failed to delete the key")

def reckless_menu():
    gui.create_menu(buttons=[
        ("Show recovery phrase", show_mnemonic),
        ("Save key to memory", save_entropy),
        ("Delete key from memory", delete_entropy)
        ], cb_back=show_main)


def show_main():
    gui.create_menu(buttons=[
        ("Wallets", wallets_menu),
        ("Master keys", xpubs_menu),
        ("Sign transaction", scan_transaction),
        ("Verify address", scan_address),
        ("Use another password", ask_for_password),
        ("Switch network (%s)" % network["name"], network_menu),
        ("# Reckless", reckless_menu)
        ])

def get_new_mnemonic(words=12):
    entropy_len = words*4//3
    global entropy
    entropy = bytes([urandom.getrandbits(8) for i in range(entropy_len)])
    return bip39.mnemonic_from_bytes(entropy)

def gen_new_key(words=12):
    mnemonic = get_new_mnemonic(words)
    screens.new_mnemonic(mnemonic, cb_continue=ask_for_password, cb_back=show_init, cb_update=get_new_mnemonic)

def recover_key():
    screens.ask_for_mnemonic(cb_continue=mnemonic_entered, cb_back=show_init, check_mnemonic=bip39.mnemonic_is_valid, words_lookup=bip39.find_candidates)

def mnemonic_entered(mnemonic):
    global entropy
    entropy = bip39.mnemonic_to_bytes(mnemonic)
    ask_for_password()

def load_key():
    global entropy
    try:
        with open(reckless_fname, "r") as f:
            d = json.loads(f.read())
        entropy = unhexlify(d["entropy"])
        ask_for_password()
    except:
        gui.error("Something went wrong, sorry")

def show_init():
    buttons = [
        ("Generate new key", gen_new_key),
        ("Enter recovery phrase", recover_key)
    ]
    # check if reckless.json file exists
    # os.path is not implemented in micropython :(
    try:
        with open(reckless_fname,"r") as f:
            c = f.read()
            if len(c) == 0:
                raise RuntimeError("File is empty")
        # if ok - add an extra button
        buttons.append(("Load key from memory", load_key))
    except:
        pass
    screens.create_menu(buttons=buttons)

def ask_for_password():
    screens.ask_for_password(init_keys)

def init_keys(password):
    mnemonic = bip39.mnemonic_from_bytes(entropy)
    seed = bip39.mnemonic_to_seed(mnemonic, password)
    keystore.load_seed(seed)
    # choose testnet by default
    select_network("test")
    show_main()

def main(blocking=True):
    gui.init()
    show_init()
    if blocking:
        while True:
            gui.update()
            qr_scanner.update()

if __name__ == '__main__':
    main()