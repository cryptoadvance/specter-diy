from unittest import TestCase, skip
from .controller import sim
from .rpc import prepare_rpc
import random
import time
from embit.descriptor import Descriptor
from embit.bip32 import HDKey
from embit.networks import NETWORKS
from embit.psbt import PSBT, DerivationPath
from embit.transaction import Transaction, TransactionInput, TransactionOutput
from embit import ec, bip32
from embit.script import Witness

rpc = prepare_rpc()
wdefault = rpc.wallet("")
wallet_prefix = "test/"+random.randint(0,0xFFFFFFFF).to_bytes(4,'big').hex()

class RPCTest(TestCase):
    """Complete tests with Core on regtest - should catch problems with signing of transactions"""

    def sign_with_descriptor(self, wname, d1, d2):
        # to derive addresses
        desc1 = Descriptor.from_string(d1)
        desc2 = Descriptor.from_string(d2)
        # recv addr 2
        addr1 = desc1.derive(2).address(NETWORKS['regtest'])
        # change addr 3
        addr2 = desc2.derive(3).address(NETWORKS['regtest'])
        res = sim.query(f"bitcoin:{addr1}?index=2", [True])
        # check it's found
        self.assertFalse(b"Can't find wallet" in res)

        # to add checksums
        d1 = rpc.getdescriptorinfo(d1)["descriptor"]
        d2 = rpc.getdescriptorinfo(d2)["descriptor"]
        rpc.createwallet(wname, True, True)
        w = rpc.wallet(wname)
        res = w.importmulti([{
                "desc": d1,
                "internal": False,
                "timestamp": "now",
                "watchonly": True,
                "range": 10,
            },{
                "desc": d2,
                "internal": True,
                "timestamp": "now",
                "watchonly": True,
                "range": 10,
            }],{"rescan": False})
        self.assertTrue(all([k["success"] for k in res]))
        wdefault.sendtoaddress(addr1, 0.1)
        rpc.mine()
        psbt = w.walletcreatefundedpsbt([], [{wdefault.getnewaddress(): 0.002}], 0, {"includeWatching": True, "changeAddress": addr2}, True)
        unsigned = psbt["psbt"].encode()
        # confirm signing
        signed = sim.query(b"sign "+unsigned, [True])
        # signed tx
        combined = rpc.combinepsbt([unsigned.decode(), signed.decode()])
        final = rpc.finalizepsbt(combined)
        self.assertTrue(final["complete"])
        # broadcast
        res = rpc.sendrawtransaction(final["hex"])
        rpc.mine()
        self.assertEqual(len(bytes.fromhex(res)), 32)

    def test_wpkh(self):
        """Native segwit single-sig"""
        path = "84h/1h/0h"
        fgp = sim.query("fingerprint").decode()
        xpub = sim.query(f"xpub m/{path}").decode()
        # normalize for regtest
        hd = HDKey.from_string(xpub)
        xpub = hd.to_string(NETWORKS["regtest"]["xpub"])
        d1 = f"wpkh([{fgp}/{path}]{xpub}/0/*)"
        d2 = f"wpkh([{fgp}/{path}]{xpub}/1/*)"
        wname = wallet_prefix+"_wpkh"
        self.sign_with_descriptor(wname, d1, d2)

    def test_sh_wpkh(self):
        """Native segwit single-sig"""
        path = "49h/1h/0h"
        fgp = sim.query("fingerprint").decode()
        xpub = sim.query(f"xpub m/{path}").decode()
        # normalize for regtest
        hd = HDKey.from_string(xpub)
        xpub = hd.to_string(NETWORKS["regtest"]["xpub"])
        d1 = f"sh(wpkh([{fgp}/{path}]{xpub}/0/*))"
        d2 = f"sh(wpkh([{fgp}/{path}]{xpub}/1/*))"
        # combined with default derivation {0,1}/*
        d3 = f"sh(wpkh([{fgp}/{path}]{xpub}"+ "/{0,1}/*))"
        wname = wallet_prefix+"_sh_wpkh"
        res = sim.query("addwallet shwpkh&"+d3, [True])
        self.sign_with_descriptor(wname, d1, d2)

    def test_strange_derivation(self):
        path = "84h/1h/0h"
        fgp = sim.query("fingerprint").decode()
        xpub = sim.query(f"xpub m/{path}").decode()
        # normalize for regtest
        hd = HDKey.from_string(xpub)
        xpub = hd.to_string(NETWORKS["regtest"]["xpub"])
        d1 = f"wpkh([{fgp}/{path}]{xpub}/44/8/*)"
        d2 = f"wpkh([{fgp}/{path}]{xpub}/55/8/*)"
        # combined with default derivation {0,1}/*
        d3 = f"wpkh([{fgp}/{path}]{xpub}"+ "/{44,55}/8/*)"
        res = sim.query("addwallet weird&"+d3, [True])
        wname = wallet_prefix+"_weird"
        self.sign_with_descriptor(wname, d1, d2)

    def test_wsh(self):
        cosigner = "[12345678/41h/2h/0h]tpubDCUwbXdGiV5qFWMyaHBfdtDv1AZtUJmENrLMGEooEdyYka1Gk5FrBdoTp54EFWxopWi9H7udD4d8CxMNa2GUECRCodbBkd4eZfiQzbMXWU3"
        path = "49h/1h/0h/2h"
        fgp = sim.query("fingerprint").decode()
        xpub = sim.query(f"xpub m/{path}").decode()
        # normalize for regtest
        hd = HDKey.from_string(xpub)
        xpub = hd.to_string(NETWORKS["regtest"]["xpub"])
        d1 = f"wsh(sortedmulti(1,[{fgp}/{path}]{xpub}/0/*,{cosigner}/0/*))"
        d2 = f"wsh(sortedmulti(1,[{fgp}/{path}]{xpub}/1/*,{cosigner}/1/*))"
        # combined with default derivation {0,1}/*
        d3 = f"wsh(sortedmulti(1,[{fgp}/{path}]{xpub}/" + "{0,1}/*" + f",{cosigner}/"+"{0,1}/*))"
        res = sim.query("addwallet wsh&"+d3, [True])
        wname = wallet_prefix+"_wsh"
        self.sign_with_descriptor(wname, d1, d2)

    def test_sh_wsh(self):
        cosigner = "[12345678/41h/2h/0h]tpubDCUwbXdGiV5qFWMyaHBfdtDv1AZtUJmENrLMGEooEdyYka1Gk5FrBdoTp54EFWxopWi9H7udD4d8CxMNa2GUECRCodbBkd4eZfiQzbMXWU3"
        path = "49h/1h/0h/2h"
        fgp = sim.query("fingerprint").decode()
        xpub = sim.query(f"xpub m/{path}").decode()
        # normalize for regtest
        hd = HDKey.from_string(xpub)
        xpub = hd.to_string(NETWORKS["regtest"]["xpub"])
        d1 = f"sh(wsh(multi(1,[{fgp}/{path}]{xpub}/0/*,{cosigner}/0/*)))"
        d2 = f"sh(wsh(multi(1,[{fgp}/{path}]{xpub}/1/*,{cosigner}/1/*)))"
        # combined with default derivation {0,1}/*
        d3 = f"sh(wsh(multi(1,[{fgp}/{path}]{xpub}/" + "{0,1}/*" + f",{cosigner}/"+"{0,1}/*)))"
        res = sim.query("addwallet shwsh&"+d3, [True])
        wname = wallet_prefix+"_sh_wsh"
        self.sign_with_descriptor(wname, d1, d2)

    def test_weird_wsh(self):
        cosigner = "[12345678/41h/2h/0h]tpubDCUwbXdGiV5qFWMyaHBfdtDv1AZtUJmENrLMGEooEdyYka1Gk5FrBdoTp54EFWxopWi9H7udD4d8CxMNa2GUECRCodbBkd4eZfiQzbMXWU3"
        path = "49h/1h/0h/2h"
        fgp = sim.query("fingerprint").decode()
        xpub = sim.query(f"xpub m/{path}").decode()
        # normalize for regtest
        hd = HDKey.from_string(xpub)
        xpub = hd.to_string(NETWORKS["regtest"]["xpub"])
        d1 = f"wsh(sortedmulti(1,[{fgp}/{path}]{xpub}/5/*,{cosigner}/2/5/*))"
        d2 = f"wsh(sortedmulti(1,[{fgp}/{path}]{xpub}/8/*,{cosigner}/3/5/*))"
        # combined with default derivation {0,1}/*
        d3 = f"wsh(sortedmulti(1,[{fgp}/{path}]{xpub}/" + "{5,8}/*" + f",{cosigner}/"+"{2,3}/5/*))"
        res = sim.query("addwallet wshmeh&"+d3, [True])
        wname = wallet_prefix+"_wshmeh"
        self.sign_with_descriptor(wname, d1, d2)

    def test_miniscript(self):
        # and(pk(A),after(100)) -> and_v(v:pk(A),after(100))
        path = "49h/1h/0h/2h"
        fgp = sim.query("fingerprint").decode()
        xpub = sim.query(f"xpub m/{path}").decode()
        desc = f"wsh(and_v(v:pk([{fgp}/{path}]{xpub}"+"/{0,1}/*),after(10)))"
        res = sim.query("addwallet mini&"+desc, [True])
        wname = wallet_prefix+"_mini"
        d = Descriptor.from_string(desc)
        d1 = d.derive(2, branch_index=0)
        d2 = d.derive(3, branch_index=1)
        # recv addr 2
        addr1 = d1.address(NETWORKS['regtest'])
        # change addr 3
        addr2 = d2.address(NETWORKS['regtest'])
        res = sim.query(f"bitcoin:{addr1}?index=2", [True])
        # check it's found
        self.assertFalse(b"Can't find wallet" in res)

        rpc.createwallet(wname, True, True)
        w = rpc.wallet(wname)
        res = w.importmulti([{
                "scriptPubKey": {"address": addr1},#d1.script_pubkey().data.hex(),
                # "witnessscript": d1.witness_script().data.hex(),
                # "pubkeys": [k.sec().hex() for k in d1.keys],
                "internal": False,
                "timestamp": "now",
                "watchonly": True,
            },{
                "scriptPubKey": {"address": addr2},#d2.script_pubkey().data.hex(),
                # "witnessscript": d2.witness_script().data.hex(),
                # "pubkeys": [k.sec().hex() for k in d2.keys],
                "internal": True,
                "timestamp": "now",
                "watchonly": True,
            }],{"rescan": False})
        self.assertTrue(all([k["success"] for k in res]))
        wdefault.sendtoaddress(addr1, 0.1)
        rpc.mine()
        unspent = w.listunspent()
        self.assertTrue(len(unspent) > 0)
        unspent = [{"txid": u["txid"], "vout": u["vout"]} for u in unspent[:1]]
        tx = w.createrawtransaction(unspent, [{wdefault.getnewaddress(): 0.002},{addr2: 0.09799}])
        psbt = PSBT.from_base64(w.converttopsbt(tx))
        # locktime magic :)
        psbt.tx.locktime = 11
        psbt.tx.vin[0].sequence = 10
        # fillinig psbt with data
        psbt.inputs[0].witness_script = d1.witness_script()
        pub = ec.PublicKey.parse(d1.keys[0].sec())
        psbt.inputs[0].bip32_derivations[pub] = DerivationPath(bytes.fromhex(fgp), bip32.parse_path(f"m/{path}")+[0,2])
        tx = w.gettransaction(unspent[0]["txid"])
        t = Transaction.from_string(tx["hex"])
        psbt.inputs[0].witness_utxo = t.vout[unspent[0]["vout"]]

        psbt.outputs[1].witness_script = d2.witness_script()
        pub2 = ec.PublicKey.parse(d2.keys[0].sec())
        psbt.outputs[1].bip32_derivations[pub2] = DerivationPath(bytes.fromhex(fgp), bip32.parse_path(f"m/{path}")+[1,3])

        unsigned = psbt.to_base64()
        # confirm signing
        signed = sim.query("sign "+unsigned, [True])
        stx = PSBT.from_base64(signed.decode())
        # signed tx
        t = psbt.tx
        # print(stx)
        t.vin[0].witness = Witness([stx.inputs[0].partial_sigs[pub], psbt.inputs[0].witness_script.data])
        # broadcast
        with self.assertRaises(Exception):
            res = rpc.sendrawtransaction(t.serialize().hex())
        rpc.mine(11)
        res = rpc.sendrawtransaction(t.serialize().hex())
        rpc.mine()
        self.assertEqual(len(bytes.fromhex(res)), 32)


    def test_with_private(self):
        pass

    def test_sighashes(self):
        pass
