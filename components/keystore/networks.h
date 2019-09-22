#ifndef __NETWORKS_H__
#define __NETWORKS_H__

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>

typedef struct {
	char * name; // Testnet / Mainnet / Regtest / Signet
	uint8_t wif;
	// address prefixes
	uint8_t p2pkh;
	uint8_t p2sh;
	char bech32[5];
	// bip32 prefixes
	uint32_t xprv;
	uint32_t xpub;
	// slip132 prefixes
	uint32_t yprv;
	uint32_t zprv;
	uint32_t Yprv;
	uint32_t Zprv;
	uint32_t ypub;
	uint32_t zpub;
	uint32_t Ypub;
	uint32_t Zpub;
	// coin type
	uint32_t bip32;
} network_t;

extern const network_t Mainnet;
extern const network_t Testnet;
extern const network_t Regtest;
extern const network_t Signet;

#define NETWORKS_NUM	4
extern const network_t * networks[NETWORKS_NUM];

#ifdef __cplusplus
}
#endif

#endif //__NETWORKS_H__