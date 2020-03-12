import gui
from gui import screens, popups
from gui.decorators import cb_with_args
import gui.common
import lvgl as lv

import utime as time
import os, gc, sys
import ujson as json
# hex and base64 encoding
from ubinascii import hexlify, unhexlify, a2b_base64, b2a_base64

from bitcoin import bip39, bip32, psbt, script
from bitcoin.networks import NETWORKS
from keystore import KeyStore

from qrscanner import QRScanner
from usbhost import USBHost
from rng import get_random_bytes

from pin import Secret, Key
from platform import simulator, storage_root, USB_ENABLED, DEV_ENABLED
from ucryptolib import aes
from hashlib import hmac_sha512

from io import BytesIO

reckless_fname = "%s/%s" % (storage_root, "reckless.json")

qr_scanner = QRScanner()
usb_host = USBHost()

# entropy that will be converted to mnemonic
entropy = None
# network we are using
network = None
# our key storage
keystore = KeyStore(storage_root=storage_root)

DEFAULT_XPUBS = []
ALL_XPUBS = []

SUPPORTED_SCRIPTS = {
    "p2wpkh": "Native Segwit",
    "p2sh-p2wpkh": "Nested Segwit",
    "p2wsh-sortedmulti": "Native Segwit Multisig",
    "p2sh-p2wsh-sortedmulti": "Nested Segwit Multisig",
}

def catchit(fn):
    """ Catches an error in the function and 
        displays error screen with exception """
    # Maybe there is a better way... 
    def cb(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            b = BytesIO()
            sys.print_exception(e, b)
            gui.error("Something bad happened...\n\n%s" % b.getvalue().decode())
    return cb

@catchit
def cancel_scan():
    print("Cancel scan!")
    qr_scanner.stop()
    show_main()

@catchit
def del_wallet(w):
    keystore.delete_wallet(w)
    wallets_menu()

@catchit
def select_wallet(w):
    popups.show_wallet(w, delete_cb=del_wallet)

@catchit
def new_wallet_confirm(name, descriptor):
    # print("creating wallet %s:" % name,descriptor)
    keystore.create_wallet(name, descriptor)

@catchit
def parse_new_wallet(s):
    show_main()
    gui.update(30)

    # wallet format:
    # name&descriptor
    arr = s.split("&")
    if len(arr) != 2:
        gui.error("Invalid wallet format")
        return
    w = keystore.check_new_wallet(*arr)
    keys_str = []
    for key in w.keys:
        k = ("%r" % key).replace("]", "]\n")
        if keystore.owns_key(key):
            keys_str.append("#7ED321 My key: # %s" % k)
        else:
            keys_str.append("#F5A623 External key: # %s" % k)
    keys = "\n\n".join(keys_str)
    if w.script_type not in SUPPORTED_SCRIPTS.keys():
        raise ValueError("Script type \"%s\" is not supported" % w.script_type)
    sc = w.script_type
    msg = "Policy: %s\nScript: %s\n%s\n\n%s" % (w.policy, SUPPORTED_SCRIPTS[w.script_type], sc, keys)

    scr = popups.prompt("Add wallet \"%s\"?" % arr[0], msg, ok=cb_with_args(new_wallet_confirm, name=arr[0], descriptor=arr[1]))
    scr.message.set_recolor(True)

@catchit
def add_new_wallet():
    screens.show_progress("Scan wallet to add",
                          "Scanning.. Click \"Cancel\" to stop.",
                          callback=cancel_scan)
    gui.update(30)
    qr_scanner.start_scan(parse_new_wallet, qr_animated, add_new_wallet)

@catchit
def wallets_menu():
    buttons = []
    def wrapper(w):
        def cb():
            select_wallet(w)
        return cb
    for wallet in keystore.wallets:
        buttons.append((wallet.name, wrapper(wallet)))
    buttons.append((lv.SYMBOL.PLUS+" Add new wallet (scan)", add_new_wallet))
    gui.create_menu(buttons=buttons, cb_back=show_main, title="Select the wallet")

@catchit
def show_xpub(name, derivation, xpub=None):
    xpubs_menu()
    gui.update(30)
    try:
        if xpub is None:
            xpub = keystore.get_xpub(derivation)
        prefix = "[%s]" % bip32.path_to_str(bip32.parse_path(derivation), fingerprint=keystore.fingerprint)
    except:
        gui.error("Derivation path \"%s\" doesn't look right..." % derivation)
        return
    xpub_str = xpub.to_base58(network["xpub"])
    slip132 = xpub.to_base58()
    if slip132 == xpub_str:
        slip132 = None
    popups.show_xpub(name, xpub_str, slip132=slip132, prefix=prefix)

@catchit
def get_custom_xpub_path():
    def cb(derivation):
        show_xpub("Custom path key", derivation)
    screens.ask_for_derivation(cb, xpubs_menu)

@catchit
def more_xpubs_menu():
    def selector(name, derivation):
        def cb():
            show_xpub("Master "+name, derivation)
        return cb
    buttons = []
    for name, derivation in ALL_XPUBS:
        buttons.append((name, selector(name, derivation)))
    buttons.append(("Enter custom derivation", get_custom_xpub_path))
    gui.create_menu(buttons=buttons, cb_back=xpubs_menu, title="Select the master key")

@catchit
def xpubs_menu():
    def selector(name, derivation):
        def cb():
            show_xpub("Master "+name, derivation)
        return cb
    buttons = []
    for name, derivation in DEFAULT_XPUBS:
        buttons.append((name, selector(name, derivation)))
    buttons.append(("Show more keys", more_xpubs_menu))
    buttons.append(("Enter custom derivation", get_custom_xpub_path))
    gui.create_menu(buttons=buttons, cb_back=show_main, title="Select the master key")

@catchit
def sign_psbt(wallet=None, tx=None, success_callback=None):
    wallet.fill_psbt(tx)
    keystore.sign(tx)
    # remove everything but partial sigs
    # to reduce QR code size
    tx.unknown = {}
    tx.xpubs = {}
    for i in range(len(tx.inputs)):
        tx.inputs[i].unknown = {}
        tx.inputs[i].non_witness_utxo = None
        tx.inputs[i].witness_utxo = None
        tx.inputs[i].sighash_type = None
        tx.inputs[i].bip32_derivations = {}
        tx.inputs[i].witness_script = None
        tx.inputs[i].redeem_script = None
    for i in range(len(tx.outputs)):
        tx.outputs[i].unknown = {}
        tx.outputs[i].bip32_derivations = {}
        tx.outputs[i].witness_script = None
        tx.outputs[i].redeem_script = None
    b64_tx = b2a_base64(tx.serialize()).decode('utf-8')
    if b64_tx[-1:] == "\n":
        b64_tx = b64_tx[:-1]
    popups.qr_alert("Signed transaction:", b64_tx, "Scan it with your software wallet", width=520)
    if success_callback is not None:
        success_callback(b64_tx)

@catchit
def parse_transaction(b64_tx, success_callback=None, error_callback=None):
    # we will go to main afterwards
    show_main()
    try:
        raw = a2b_base64(b64_tx)
        tx = psbt.PSBT.parse(raw)
    except:
        gui.error("Failed at transaction parsing")
        if error_callback is not None:
            error_callback("invalid argument")
        return
    # blue wallet trick - if the fingerprint is 0 we use our fingerprint
    for scope in [tx.inputs, tx.outputs]:
        for el in scope:
            for der in el.bip32_derivations:
                if el.bip32_derivations[der].fingerprint == b'\x00\x00\x00\x00':
                    el.bip32_derivations[der].fingerprint = keystore.fingerprint
    try:
        data = keystore.check_psbt(tx)
    except Exception as e:
        gui.error("Problem with the transaction: %r" % e)
        if error_callback is not None:
            error_callback("invalid argument")
        return
    title = "Spending %u\nfrom %s" % (data["spending"], data["wallet"].name)
    popups.prompt_tx(title, data,
        ok=cb_with_args(sign_psbt, wallet=data["wallet"], tx=tx, success_callback=success_callback), 
        cancel=cb_with_args(error_callback, "user cancel")
    )

def qr_animated(indx, callback):
    gui.alert("Animated QR: %s/%s" % (indx[0], indx[1]), "Proceed to scanning code No. %s" % str(indx[0]+1), callback)

@catchit
def scan_transaction():
    screens.show_progress("Scan transaction to sign",
                          "Scanning.. Click \"Cancel\" to stop.",
                          callback=cancel_scan)
    gui.update(30)
    qr_scanner.start_scan(parse_transaction, qr_animated, scan_transaction)

@catchit
def verify_address(s):
    # we will go to main afterwards
    show_main()
    # verifies address in the form [bitcoin:]addr?index=i
    s = s.replace("bitcoin:", "")
    arr = s.split("?")
    index = None
    addr = None
    # check that ?index= is there
    if len(arr) > 1:
        addr = arr[0]
        meta_arr = arr[1].split("&")
        # search for `index=`
        for meta in meta_arr:
            if meta.startswith("index="):
                try:
                    index = int(meta.split("=")[1])
                except:
                    gui.error("Index is not an integer...")
                    return
    if index is None or addr is None:
        # where we will go next
        gui.error("No derivation index in the address metadata - can't verify.")
        return
    for w in keystore.wallets:
        if w.address(index) == addr:
            popups.qr_alert("Address #%d from wallet\n\"%s\"" % (index+1, w.name),
                            "bitcoin:%s"%addr, message_text=addr)
            return
    gui.error("Address doesn't belong to any wallet. Wrong device or network?")

@catchit
def scan_address():
    screens.show_progress("Scan address to verify",
                          "Scanning.. Click \"Cancel\" to stop.",
                          callback=cancel_scan)
    gui.update(30)
    qr_scanner.start_scan(verify_address)

@catchit
def set_network_xpubs(net):
    while len(DEFAULT_XPUBS) > 0:
        DEFAULT_XPUBS.pop()
    DEFAULT_XPUBS.append(("Single key", "m/84h/%dh/0h" % net["bip32"]))
    DEFAULT_XPUBS.append(("Multisig", "m/48h/%dh/0h/2h" % net["bip32"]))

    while len(ALL_XPUBS) > 0:
        ALL_XPUBS.pop()
    ALL_XPUBS.append(("Single Native Segwit\nm/84h/%dh/0h" % net["bip32"], "m/84h/%dh/0h" % net["bip32"]))
    ALL_XPUBS.append(("Single Nested Segwit\nm/49h/%dh/0h" % net["bip32"], "m/49h/%dh/0h" % net["bip32"]))
    ALL_XPUBS.append(("Multisig Native Segwit\nm/48h/%dh/0h/2h" % net["bip32"], "m/48h/%dh/0h/2h" % net["bip32"]))
    ALL_XPUBS.append(("Multisig Nested Segwit\nm/48h/%dh/0h/1h" % net["bip32"], "m/48h/%dh/0h/1h" % net["bip32"]))

@catchit
def select_network(name):
    global network
    if name in NETWORKS:
        network = NETWORKS[name]
        if keystore.is_initialized:
            set_network_xpubs(network)
            # load existing wallets for this network
            keystore.load_wallets(name)
            # create a default wallet if it doesn't exist
            if len(keystore.wallets) == 0:
                # create a wallet descriptor
                # this is not exactly compatible with Bitcoin Core though.
                # '_' means 0/* or 1/* - standard receive and change 
                #                        derivation patterns
                derivation = DEFAULT_XPUBS[0][1]
                xpub = keystore.get_xpub(derivation).to_base58(network["xpub"])
                fingerprint = hexlify(keystore.fingerprint).decode('utf-8')
                prefix = "[%s%s]" % (fingerprint, derivation[1:])
                descriptor = "wpkh(%s%s/_)" % (prefix, xpub)
                keystore.create_wallet("Default", descriptor)
    else:
        raise RuntimeError("Unknown network")

@catchit
def network_menu():
    def selector(name):
        def cb():
            try:
                select_network(name)
                show_main()
            except Exception as e:
                gui.error("%r" % e)
        return cb
    # could be done with iterator
    # but order is unknown then
    gui.create_menu(buttons=[
        ("Mainnet", selector("main")),
        ("Testnet", selector("test")),
        ("Regtest", selector("regtest")),
        ("Signet", selector("signet"))
    ], title="Select the network")

@catchit
def show_mnemonic():
    # print(bip39.mnemonic_from_bytes(entropy))
    popups.show_mnemonic(bip39.mnemonic_from_bytes(entropy))

@catchit
def save_entropy():
    gui.prompt("Security", "Do you want to encrypt your key?", save_entropy_encrypted, save_entropy_plain)

@catchit
def entropy_decrypt(entropy_encrypted):
    # 2 - MODE_CBC
    crypto = aes(Key.key, 2, Key.iv)
    data = crypto.decrypt(entropy_encrypted)
    l = data[0]
    if l > 32:
        raise RuntimeError("Failed to decrypt entropy - data is corrupted")
    return data[1:l+1]

@catchit
def entropy_encrypt(entropy_plain):
    # 2 - MODE_CBC
    crypto = aes(Key.key, 2, Key.iv)
    # encrypted data should be mod 16 (blocksize)
    pad_len = 16-((len(entropy_plain)+1) % 16)
    data = bytes([len(entropy_plain)])+entropy_plain+bytes(pad_len)
    return crypto.encrypt(data);

@catchit
def save_entropy_encrypted():
    try:
        Key.iv = get_random_bytes(16)
        entropy_encrypted = entropy_encrypt(entropy)
        hmac_entropy_encrypted = hmac_sha512(Key.key, entropy_encrypted)
        obj = {
            "entropy": hexlify(entropy_encrypted).decode('utf-8'),
            "iv": hexlify(Key.iv).decode('utf-8'),
            "hmac": hexlify(hmac_entropy_encrypted).decode('utf-8')
        }
        with open(reckless_fname, "w") as f:
            f.write(json.dumps(obj))
        with open(reckless_fname, "r") as f:
            d = json.loads(f.read())
        if "entropy" in d and d["entropy"] == hexlify(entropy_encrypted).decode('utf-8') and \
                unhexlify(d["hmac"]) == hmac_entropy_encrypted and entropy == entropy_decrypt(entropy_encrypted):
            gui.alert("Success!", "Your encrypted key is saved in the memory now")
        else:
            gui.error("Something went wrong")
    except Exception as e:
        gui.error("Fail: %r" % e)

@catchit
def save_entropy_plain():
    obj = {"entropy": hexlify(entropy).decode('utf-8')}
    with open(reckless_fname, "w") as f:
        f.write(json.dumps(obj))
    with open(reckless_fname, "r") as f:
        d = json.loads(f.read())
    if "entropy" in d  and d["entropy"] == hexlify(entropy).decode('utf-8'):
        gui.alert("Success!", "Your key is saved in the memory now")
    else:
        gui.error("Something went wrong")

@catchit
def delete_entropy():
    try:
        os.remove(reckless_fname)
        gui.alert("Success!", "Your key is deleted")
    except:
        gui.error("Failed to delete the key")

@catchit
def save_settings(config):
    try:
        if USB_ENABLED and not config["usb"]:
            os.remove("%s/%s" % (storage_root, "USB_ENABLED"))
        if not USB_ENABLED and config["usb"]:
            with open("%s/%s" % (storage_root, "USB_ENABLED"), "w") as f:
                f.write("dummy") # should be hmac instead
        if DEV_ENABLED and not config["developer"]:
            os.remove("%s/%s" % (storage_root, "DEV_ENABLED"))
        if not DEV_ENABLED and config["developer"]:
            with open("%s/%s" % (storage_root, "DEV_ENABLED"), "w") as f:
                f.write("dummy") # should be hmac instead
        time.sleep_ms(100)
        if simulator:
            # meh... kinda doesn't work on unixport
            sys.exit()
        else:
            import pyb
            pyb.hard_reset()
    except Exception as e:
        gui.error("Failed to update settings!\n%r" % e)
    print(config)

@catchit
def settings_menu():
    gui.create_menu(buttons=[
        ("Show recovery phrase", show_mnemonic),
        ("Save key to memory", save_entropy),
        ("Delete key from memory", delete_entropy),
        ("Security settings", 
            cb_with_args(popups.show_settings, 
                         {"usb": USB_ENABLED, "developer": DEV_ENABLED}, 
                         save_settings)),
        ], cb_back=show_main,title="Careful. Think twice.")

@catchit
def show_main():
    gui.create_menu(buttons=[
        ("Wallets", wallets_menu),
        ("Master public keys", xpubs_menu),
        ("Sign transaction", scan_transaction),
        ("Verify address", scan_address),
        ("Use another password", ask_for_password),
        ("Switch network (%s)" % network["name"], network_menu),
        ("Settings", settings_menu)
        ])

@catchit
def get_new_mnemonic(words=12):
    entropy_len = words*4//3
    global entropy
    entropy = get_random_bytes(entropy_len)
    return bip39.mnemonic_from_bytes(entropy)

@catchit
def gen_new_key(words=12):
    mnemonic = get_new_mnemonic(words)
    screens.new_mnemonic(mnemonic,
                         cb_continue=ask_for_password,
                         cb_back=show_init,
                         cb_update=get_new_mnemonic)

@catchit
def recover_key():
    screens.ask_for_mnemonic(cb_continue=mnemonic_entered,
                             cb_back=show_init,
                             check_mnemonic=bip39.mnemonic_is_valid,
                             words_lookup=bip39.find_candidates)

@catchit
def mnemonic_entered(mnemonic):
    global entropy
    entropy = bip39.mnemonic_to_bytes(mnemonic.strip())
    ask_for_password()

@catchit
def load_key():
    global entropy
    with open(reckless_fname, "r") as f:
        d = json.loads(f.read())
        entropy = unhexlify(d["entropy"])
    if "hmac" in d:
        hmac_calc = hmac_sha512(Key.key, entropy)
        if unhexlify(d["hmac"]) != hmac_calc:
            raise ValueError('Hmac does not match!')
        Key.iv = unhexlify(d["iv"])
        entropy = entropy_decrypt(entropy)
    if entropy is not None:
        ask_for_password()
    else:
        gui.error("Failed to load your recovery phrase.")

@catchit
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
                raise RuntimeError("%s file is empty" % reckless_fname)
        # if ok - add an extra button
        buttons.append(("Load key from memory", load_key))
    except:
        pass
    screens.create_menu(buttons=buttons)

@catchit
def ask_for_password():
    screens.ask_for_password(init_keys)

@catchit
def init_keys(password):
    mnemonic = bip39.mnemonic_from_bytes(entropy)
    seed = bip39.mnemonic_to_seed(mnemonic, password)
    keystore.load_seed(seed)
    # choose testnet by default
    select_network("test")
    gc.collect()
    show_main()
    if usb_host.callback is None:
        usb_host.callback = host_callback

# process all usb commands
@catchit
def host_callback(data):
    # close all existing popups
    popups.close_all_popups()

    if data=="fingerprint":
        usb_host.respond(hexlify(keystore.fingerprint).decode('ascii'))
        return

    if data.startswith("xpub "):
        path = data[5:].strip(" /\r\n")
        try:
            if path == "m":
                hd = keystore.root.to_public()
            else:
                hd = keystore.get_xpub(path)
            xpub = hd.to_base58(network["xpub"])
            usb_host.respond(xpub)

            show_xpub("Master key requested from host:", path, xpub)
        except Exception as e:
            print(e)
            usb_host.respond("error: bad derivation path '%s'" % path)
        return

    if data.startswith("sign "):
        def success_cb(signed_tx):
            usb_host.respond(signed_tx)
        def error_cb(error):
            usb_host.respond("error: %s" % error)
        parse_transaction(data[5:], success_callback=success_cb, error_callback=error_cb)
        return

    if data.startswith("showaddr "):
        arr = data.split(" ")
        path = arr[-1].strip()
        addrtype = "wpkh"
        if len(arr) > 2:
            addrtype = arr[-2].strip()
        # TODO: detect wallet this address belongs to
        try:
            key = keystore.get_xpub(path)
            if addrtype == "wpkh":
                sc = script.p2wpkh(key)
            elif addrtype == "pkh":
                sc = script.p2pkh(key)
            elif addrtype == "sh-wpkh":
                sc = script.p2sh(script.p2wpkh(key))
            else:
                raise RuntimeError()
            addr=sc.address(network)
            usb_host.respond(addr)
            popups.qr_alert("Address with path %s\n(requested by host)" % (path),
                            "bitcoin:"+addr, message_text=addr)

        except Exception as e:
            print(e)
            usb_host.respond("error: invalid argument")
        return

    if data.startswith("importwallet "):
        parse_new_wallet(data[13:])

    # TODO: 
    # - signmessage <message>
    # - showdescraddr <descriptor>

def qr_scanner_error(msg):
    cancel_scan()
    gui.error(msg)

def update(dt=30):
    gui.update(dt)
    qr_scanner.update(qr_scanner_error)
    usb_host.update()

def ioloop():
    while True:
        time.sleep_ms(30)
        update(30)

def main(blocking=True):
    # FIXME: check for all ports (unix, js, stm)
    # what is available in os module
    # maybe we can check it without try-except
    try:
        os.mkdir(storage_root)
    except:
        pass
    # schedules display autoupdates if blocking=False
    # it may cause GUI crashing when out of memory
    # but perfect to debug
    gui.init(blocking)
    ret = Secret.load_secret()
    if ret == False:
        Secret.generate_secret()
    screens.ask_pin(not ret, show_init)
    if blocking:
        ioloop()

if __name__ == '__main__':
    main()
