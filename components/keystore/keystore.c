#include "keystore.h"
#include "helpers.h"
#include <stdio.h>
#include "wally_crypto.h"
#include "wally_bip32.h"
#include "wally_bip39.h"
#include "wally_address.h"
#include "wally_script.h"

static uint32_t * parse_derivation(const char * path, size_t * derlen){
    static const char VALID_CHARS[] = "0123456789/'h";
    size_t len = strlen(path);
    const char * cur = path;
    if(path[0] == 'm'){ // remove leading "m/"
        cur+=2;
        len-=2;
    }
    if(cur[len-1] == '/'){ // remove trailing "/"
        len--;
    }
    size_t derivationLen = 1;
    // checking if all chars are valid and counting derivation length
    for(size_t i=0; i<len; i++){
        const char * pch = strchr(VALID_CHARS, cur[i]);
        if(pch == NULL){ // wrong character
            return NULL;
        }
        if(cur[i] == '/'){
            derivationLen++;
        }
    }
    uint32_t * derivation = (uint32_t *)calloc(derivationLen, sizeof(uint32_t));
    size_t current = 0;
    for(size_t i=0; i<len; i++){
        if(cur[i] == '/'){ // next
            current++;
            continue;
        }
        const char * pch = strchr(VALID_CHARS, cur[i]);
        uint32_t val = pch-VALID_CHARS;
        if(derivation[current] >= BIP32_INITIAL_HARDENED_CHILD){ // can't have anything after hardened
            free(derivation);
            return NULL;
        }
        if(val < 10){
            derivation[current] = derivation[current]*10 + val;
        }else{ // h or ' -> hardened
            derivation[current] += BIP32_INITIAL_HARDENED_CHILD;
        }
    }
    *derlen = derivationLen;
    return derivation;
}

int keystore_init(const char * mnemonic, const char * password, keystore_t * key){
	if(key == NULL){
		return -1;
	}
	if(mnemonic == NULL){
		key->root = NULL;
	}
	if(key->root == NULL){
		bip32_key_free(key->root);
		key->root = NULL;
	}
	int res;
	size_t len;
    uint8_t seed[BIP39_SEED_LEN_512];
    res = bip39_mnemonic_to_seed(mnemonic, password, seed, sizeof(seed), &len);
    res = bip32_key_from_seed_alloc(seed, sizeof(seed), BIP32_VER_TEST_PRIVATE, 0, &key->root);
    wally_bzero(seed, sizeof(seed));
    uint8_t h160[20];
    wally_hash160(key->root->pub_key, sizeof(key->root->pub_key),
                  h160, sizeof(h160));
    for(int i=0; i<4; i++){
    	sprintf(key->fingerprint+2*i, "%02x", h160[i]);
    }
	return 0;
}

int keystore_get_xpub(const keystore_t * key, const char * path, const network_t * network, char ** xpub){
	struct ext_key * child = NULL;
	int res;
	size_t len = 0;
	uint32_t * derivation = parse_derivation(path, &len);
	if(derivation == NULL){
		return -1;
	}
	res = bip32_key_from_parent_path_alloc(key->root, derivation, len, BIP32_FLAG_KEY_PRIVATE, &child);
	child->version = network->xprv;
    res = bip32_key_to_base58(child, BIP32_FLAG_KEY_PUBLIC, xpub);	
    bip32_key_free(child);
    free(derivation);
    return 0;
}

int keystore_get_addr(const keystore_t * key, const char * path, const network_t * network, char ** addr, int flag){
    struct ext_key * child = NULL;
    int res;
    size_t len = 0;
    uint32_t * derivation = parse_derivation(path, &len);
    if(derivation == NULL){
        return -1;
    }
    res = bip32_key_from_parent_path_alloc(key->root, derivation, len, BIP32_FLAG_KEY_PRIVATE, &child);
    child->version = network->xprv;

    if(flag == KEYSTORE_BECH32_ADDRESS){
        res |= wally_bip32_key_to_addr_segwit(child, network->bech32, 0, addr);
    }else{
        res |= wally_bip32_key_to_address(child, WALLY_ADDRESS_TYPE_P2SH_P2WPKH, network->p2sh, addr);
    }
    bip32_key_free(child);
    free(derivation);
    if(res!=WALLY_OK){
        wally_free_string(*addr);
    }
    return res;
}

int keystore_check_psbt(const keystore_t * key, const struct wally_psbt * psbt){
    // check inputs: at least one to sign
    uint8_t err = KEYSTORE_PSBTERR_CANNOT_SIGN;
    uint8_t h160[20];
    wally_hash160(key->root->pub_key, sizeof(key->root->pub_key),
                  h160, sizeof(h160));
    for(int i=0; i<psbt->num_inputs; i++){
        // check fingerprints in derivations
        if(psbt->inputs[i].keypaths == NULL){
            return KEYSTORE_PSBTERR_CANNOT_SIGN;
        }
        uint8_t can_sign = 0;
        for(int j=0; j<psbt->inputs[i].keypaths->num_items; j++){
            if(memcmp(psbt->inputs[i].keypaths->items[j].origin.fingerprint, h160, 4)==0){
                can_sign = 1;
                break;
            }
        }
        if(can_sign){
            err = 0;
        }else{
            if(err == 0){ // if can't sign but could sign previous
                return KEYSTORE_PSBTERR_MIXED_INPUTS;
            }
        }
        // TODO: add verification that all inputs correspond to the same policy
        // just forcing single key for now
        if(psbt->inputs[i].keypaths->num_items != 1){
            return KEYSTORE_PSBTERR_UNSUPPORTED_POLICY;
        }
    }
    // TODO: check all fields in the psbt
    return err;
}

int keystore_output_is_change(const keystore_t * key, const struct wally_psbt * psbt, uint8_t i, char ** warning){
    // TODO: check if it is a change
    if(i >= psbt->num_outputs){
        return 0;
    }
    
    return 0;
}

int keystore_sign_psbt(const keystore_t * key, struct wally_psbt * psbt, char ** output){
    size_t len;
    for(int i = 0; i < psbt->num_inputs; i++){
        if(!psbt->inputs[i].witness_utxo){
            return -1;
        }
        uint8_t hash[32];
        uint8_t script[25];
        wally_scriptpubkey_p2pkh_from_bytes(
            psbt->inputs[i].witness_utxo->script+2, 20,
            0,
            script, 25, &len);
        wally_tx_get_btc_signature_hash(psbt->tx, i, 
                script, len,
                psbt->inputs[i].witness_utxo->satoshi,
                WALLY_SIGHASH_ALL,
                WALLY_TX_FLAG_USE_WITNESS,
                hash, 32
            );
        struct ext_key * pk = NULL;
        // TODO: fix for multiple keypaths
        bip32_key_from_parent_path_alloc(key->root, 
            psbt->inputs[i].keypaths->items[0].origin.path, 
            psbt->inputs[i].keypaths->items[0].origin.path_len, 
            BIP32_FLAG_KEY_PRIVATE, &pk);
 
        uint8_t sig[EC_SIGNATURE_LEN];
        wally_ec_sig_from_bytes(
                pk->priv_key+1, 32, // first byte of ext_key.priv_key is 0x00
                hash, 32,
                EC_FLAG_ECDSA,
                sig, EC_SIGNATURE_LEN
            );
        uint8_t der[EC_SIGNATURE_DER_MAX_LEN+1];
        wally_ec_sig_to_der(
                sig, EC_SIGNATURE_LEN,
                der, EC_SIGNATURE_DER_MAX_LEN,
                &len
            );
        der[len] = WALLY_SIGHASH_ALL;
        if(!psbt->inputs[i].partial_sigs){
            partial_sigs_map_init_alloc(1, &psbt->inputs[i].partial_sigs);
        }
        add_new_partial_sig(psbt->inputs[i].partial_sigs,
                pk->pub_key, 
                der, len+1
            );
        bip32_key_free(pk);
    }
 
    wally_psbt_to_base64(psbt, output); 
    return 0;
}
