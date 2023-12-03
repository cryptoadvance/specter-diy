from embit.descriptor import Descriptor
from embit.networks import NETWORKS
from .rpc import prepare_rpc

def create_wallet(wname, d1: str, d2: str, rpc=None):
    if rpc is None:
        rpc = prepare_rpc()
    wdefault = rpc.wallet("")
    # to derive addresses
    desc1 = Descriptor.from_string(d1)

    # recv addr
    addr = desc1.derive(0).address(NETWORKS['regtest'])

    # to add checksums
    d1 = rpc.getdescriptorinfo(d1)["descriptor"]
    d2 = rpc.getdescriptorinfo(d2)["descriptor"]
    rpc.createwallet(wname, True, True)
    w = rpc.wallet(wname)
    info = w.getwalletinfo()
    # bitcoin core uses descriptor wallets by default so importmulti may fail
    use_descriptors = info.get("descriptors", False)
    if not use_descriptors:
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
    else:
        res = w.importdescriptors([{
                "desc": d1,
                "internal": False,
                "timestamp": "now",
                "watchonly": True,
                "active": True,
            },{
                "desc": d2,
                "internal": True,
                "timestamp": "now",
                "watchonly": True,
                "active": True,
            }])
    assert all([k["success"] for k in res])
    wdefault.sendtoaddress(addr, 0.1)
    rpc.mine()
    return w
