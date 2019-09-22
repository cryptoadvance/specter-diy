#include "networks.h"

const network_t Mainnet = {
	"Mainnet",
    0x80, // wif
    0x00, // p2pkh
    0x05, // p2sh
    "bc", // bech32
    0x0488ade4, // xprv
    0x0488b21e, // xpub
    0x049d7878, // yprv
    0x04b2430c, // zprv
    0x0295b005, // Yprv
    0x02aa7a99, // Zprv
    0x049d7cb2, // ypub
    0x04b24746, // zpub
    0x0295b43f, // Ypub
    0x02aa7ed3, // Zpub
    0 // bip32 coin type
};

const network_t Testnet = {
	"Testnet",
    0xEF, // wif
    0x6F, // p2pkh
    0xC4, // p2sh
    "tb", // bech32
    0x04358394, // tprv
    0x043587cf, // tpub
    0x044a4e28, // uprv
    0x045f18bc, // vprv
    0x024285b5, // Uprv
    0x02575048, // Vprv
    0x044a5262, // upub
    0x045f1cf6, // vpub
    0x024289ef, // Upub
    0x02575483, // Vpub
    1 // bip32 coin type
};

const network_t Regtest = {
	"Regtest",
    0xEF, // wif
    0x6F, // p2pkh
    0xC4, // p2sh
    "bcrt", // bech32
    0x04358394, // tprv
    0x043587cf, // tpub
    0x044a4e28, // uprv
    0x045f18bc, // vprv
    0x024285b5, // Uprv
    0x02575048, // Vprv
    0x044a5262, // upub
    0x045f1cf6, // vpub
    0x024289ef, // Upub
    0x02575483, // Vpub
    1 // bip32 coin type
};

const network_t Signet = {
	"Signet",
    0xD9, // wif
    0x7D, // p2pkh
    0x57, // p2sh
    "sb", // bech32
    0x04358394, // tprv
    0x043587cf, // tpub
    0x044a4e28, // uprv
    0x045f18bc, // vprv
    0x024285b5, // Uprv
    0x02575048, // Vprv
    0x044a5262, // upub
    0x045f1cf6, // vpub
    0x024289ef, // Upub
    0x02575483, // Vpub
    1 // bip32 coin type
};

const network_t * networks[4] = { &Mainnet, &Testnet, &Regtest, &Signet };
