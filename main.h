#ifndef __WALLET_H__
#define __WALLET_H__

#include "Bitcoin.h"

typedef struct {
	uint8_t fingerprint[4];
    uint32_t * derivation;
    uint8_t derivation_len;
    HDPublicKey xpub;
} xpub_t;

typedef struct {
	char name[100];
	ScriptType type;
	uint32_t address;
	uint8_t sigs_required;
	uint8_t xpubs_len;
	xpub_t * xpubs;
} wallet_t;

/** You need to define these functions in main */
void init_keys(const char * mnemonic, const char * password);
void set_network(int net);
void show_key(int type);
int get_wallets_number();
const char * get_wallet_name(int i);
int get_cosigners_number();
const char * get_cosigner_name(int i);
int load_wallet(int num);

#endif // __WALLET_H__