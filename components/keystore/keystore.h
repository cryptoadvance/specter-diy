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

typedef struct {
	struct ext_key * root;
	char fingerprint[9];
} keystore_t;

int keystore_init(const char * mnemonic, const char * password, keystore_t * key);
int keystore_get_xpub(const keystore_t * key, const char * derivation, const network_t * network, char ** xpub);

int keystore_get_addr(const keystore_t * keystore, const char * derivation, const network_t * network, char ** addr, int flag);

int keystore_check_psbt(const keystore_t * key, const struct wally_psbt * psbt);
int keystore_sign_psbt(const keystore_t * key, struct wally_psbt * psbt, char ** output);
int keystore_output_is_change(const keystore_t * key, const struct wally_psbt * psbt, uint8_t i, char ** warning);
// int keystore_clear(keystore_t * key);
// int keystore_wipe()

#ifdef __cplusplus
}
#endif

#endif // __KEYSTORE_H__