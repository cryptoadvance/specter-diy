#ifndef __KEYSTORE_H__
#define __KEYSTORE_H__

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <string.h>
#include "wally_bip32.h"
#include "wally_psbt.h"
#include "networks.h"

#define KEYSTORE_BECH32_ADDRESS		1
#define KEYSTORE_BASE58_ADDRESS		2

#define KEYSTORE_PSBTERR_CANNOT_SIGN		1
#define KEYSTORE_PSBTERR_MIXED_INPUTS		2
#define KEYSTORE_PSBTERR_WRONG_FIELDS		4
#define KEYSTORE_PSBTERR_UNSUPPORTED_POLICY	8

#define KEYSTORE_WALLET_ERR_NOT_INCLUDED	1
#define KEYSTORE_WALLET_ERR_PARSING			2
#define KEYSTORE_WALLET_ERR_WRONG_XPUB		3

typedef struct {
	struct ext_key * root;
	char fingerprint[9];
} keystore_t;

typedef struct{
	int val; 						// file kinda
	char name[100]; 				// name of the wallet
	uint32_t address; 				// address index
	const keystore_t * keystore;
	const network_t * network;
} wallet_t;

int keystore_init(const char * mnemonic, const char * password, keystore_t * key);
int keystore_get_xpub(const keystore_t * key, const char * derivation, const network_t * network, int use_slip132, char ** xpub);

int keystore_get_addr(const keystore_t * keystore, const char * derivation, const network_t * network, char ** addr, int flag);

int keystore_check_psbt(const keystore_t * key, const struct wally_psbt * psbt);
int keystore_sign_psbt(const keystore_t * key, struct wally_psbt * psbt, char ** output);
int keystore_output_is_change(const keystore_t * key, const struct wally_psbt * psbt, uint8_t i, char ** warning);

/** allocates memory for wallet names - a list of char arrays ending with empty string "" 
	network is required to distinguish between wallets for mainnet, testnet and others
 */
// pointer to the pointer to the list of pointers... there should be a better way...
int keystore_get_wallets(const keystore_t * key, const network_t * network, char *** wallets);
/** frees memory allocated by the function above */
int keystore_free_wallets(char ** wallets);

int keystore_get_wallet(const keystore_t * key, const network_t * network, int val, wallet_t * wallet);
int wallet_get_addresses(const wallet_t * wallet, char ** base58_addr, char ** bech32_addr);

/** adds wallet, returns wallet id, populates wallet with corresponding data */
int keystore_check_wallet(const keystore_t * keystore, const network_t * network, const char * buf);
int keystore_add_wallet(const keystore_t * keystore, const network_t * network, const char * buf, wallet_t * wallet);
// int keystore_clear(keystore_t * key);
// int keystore_wipe()

#ifdef __cplusplus
}
#endif

#endif // __KEYSTORE_H__