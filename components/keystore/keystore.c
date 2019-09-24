#include "keystore.h"
#include <stdio.h>
#include "wally_crypto.h"
#include "wally_bip32.h"
#include "wally_bip39.h"
#include "wally_address.h"
#include "wally_script.h"
#include "networks.h"
#include "utility/ccan/ccan/endian/endian.h"

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
    uint8_t xpub_raw[BIP32_SERIALIZED_LEN];
    res = bip32_key_serialize(child, BIP32_FLAG_KEY_PUBLIC, xpub_raw, sizeof(xpub_raw));
    uint32_t ver = cpu_to_be32(network->xpub);
    if(len > 0){
        switch(derivation[0]){
            case BIP32_INITIAL_HARDENED_CHILD+84:
            {
                ver = cpu_to_be32(network->zpub);
                break;
            }
            case BIP32_INITIAL_HARDENED_CHILD+49:
            {
                ver = cpu_to_be32(network->ypub);
                break;
            }
            case BIP32_INITIAL_HARDENED_CHILD+48:
            {
                if(len >= 4){
                    switch(derivation[3]){
                        case BIP32_INITIAL_HARDENED_CHILD+1:
                        {
                            ver = cpu_to_be32(network->Ypub);
                            break;
                        }
                        case BIP32_INITIAL_HARDENED_CHILD+2:
                        {
                            ver = cpu_to_be32(network->Zpub);
                            break;
                        }
                    }
                }
                break;
            }
        }
    }
    memcpy(xpub_raw, &ver, 4);
    // res = bip32_key_to_base58(child, BIP32_FLAG_KEY_PUBLIC, xpub);	
    res = wally_base58_from_bytes(xpub_raw, sizeof(xpub_raw), BASE58_FLAG_CHECKSUM, xpub);
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
    if(psbt->outputs[i].keypaths == NULL){
        return 0;
    }
    if(psbt->outputs[i].keypaths->num_items != 1){
        printf("keystore: multisig change detection is not supported yet\r\n");
        return 0;
    }
    struct ext_key * pk = NULL;
    // TODO: fix for multiple keypaths
    bip32_key_from_parent_path_alloc(key->root, 
        psbt->outputs[i].keypaths->items[0].origin.path, 
        psbt->outputs[i].keypaths->items[0].origin.path_len, 
        BIP32_FLAG_KEY_PRIVATE, &pk);
    size_t script_type;
    wally_scriptpubkey_get_type(psbt->tx->outputs[i].script, psbt->tx->outputs[i].script_len, &script_type);
    // should deal with all script types, only P2WPKH for now

    // doesn't matter, we just compare strings...
    // TODO: refactor with scriptpubkey instead of addresses
    const network_t * network = &Mainnet;
    char * addr = NULL;
    char * addr2 = NULL;
    uint8_t bytes[21];
    switch(script_type){
        case WALLY_SCRIPT_TYPE_P2WPKH:
            wally_addr_segwit_from_bytes(psbt->tx->outputs[i].script, psbt->tx->outputs[i].script_len, network->bech32, 0, &addr);
            wally_bip32_key_to_addr_segwit(pk, network->bech32, 0, &addr2);
            break;
        case WALLY_SCRIPT_TYPE_P2SH:
            bytes[0] = network->p2sh;
            memcpy(bytes+1, psbt->tx->outputs[i].script+2, 20);
            wally_base58_from_bytes(bytes, 21, BASE58_FLAG_CHECKSUM, &addr);
            wally_bip32_key_to_address(pk, WALLY_ADDRESS_TYPE_P2SH_P2WPKH, network->p2sh, &addr2);
            break;
        case WALLY_SCRIPT_TYPE_P2PKH:
            bytes[0] = network->p2pkh;
            memcpy(bytes+1, psbt->tx->outputs[i].script+3, 20);
            wally_base58_from_bytes(bytes, 21, BASE58_FLAG_CHECKSUM, &addr);
            wally_bip32_key_to_address(pk, WALLY_ADDRESS_TYPE_P2PKH, network->p2pkh, &addr2);
            break;
        default:
            return 0;
    }
    int res = 0;
    if(strcmp(addr, addr2) == 0){
        res = 1;
    }
    bip32_key_free(pk);
    wally_free_string(addr2);
    wally_free_string(addr);
    return res;
}

int keystore_sign_psbt(const keystore_t * key, struct wally_psbt * psbt, char ** output){
    size_t len;
    struct wally_psbt * signed_psbt;
    wally_psbt_init_alloc(
        psbt->num_inputs,
        psbt->num_outputs,
        0,
        &signed_psbt);
    wally_psbt_set_global_tx(psbt->tx, signed_psbt);
    for(int i = 0; i < psbt->num_inputs; i++){
        if(!psbt->inputs[i].witness_utxo){
            return -1;
        }
        uint8_t hash[32];
        uint8_t script[25];

        struct ext_key * pk = NULL;
        // TODO: fix for multiple keypaths
        bip32_key_from_parent_path_alloc(key->root, 
            psbt->inputs[i].keypaths->items[0].origin.path, 
            psbt->inputs[i].keypaths->items[0].origin.path_len, 
            BIP32_FLAG_KEY_PRIVATE, &pk);

        wally_scriptpubkey_p2pkh_from_bytes(pk->pub_key, EC_PUBLIC_KEY_LEN, 
                WALLY_SCRIPT_HASH160, 
                script, 25, 
                &len);

        wally_tx_get_btc_signature_hash(psbt->tx, i, 
                script, len,
                psbt->inputs[i].witness_utxo->satoshi,
                WALLY_SIGHASH_ALL,
                WALLY_TX_FLAG_USE_WITNESS,
                hash, 32
            );
 
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
        if(!signed_psbt->inputs[i].partial_sigs){
            partial_sigs_map_init_alloc(1, &signed_psbt->inputs[i].partial_sigs);
        }
        add_new_partial_sig(signed_psbt->inputs[i].partial_sigs,
                pk->pub_key, 
                der, len+1
            );
        bip32_key_free(pk);
    }
 
    wally_psbt_to_base64(signed_psbt, output);
    wally_psbt_free(signed_psbt);
    return 0;
}
