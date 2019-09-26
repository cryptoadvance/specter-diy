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
        return 0;
    }
    if(key->root != NULL){
        bip32_key_free(key->root);
        key->root = NULL;
    }
    int res;
    size_t len;
    uint8_t seed[BIP39_SEED_LEN_512];
    // FIXME: process results - something might go wrong
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

int keystore_get_xpub(const keystore_t * key, const char * path, const network_t * network, int use_slip132, char ** xpub){
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
    if((len > 0) & use_slip132){
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
    res = wally_base58_from_bytes(xpub_raw, sizeof(xpub_raw), BASE58_FLAG_CHECKSUM, xpub);
    bip32_key_free(child);
    free(derivation);
    return 0;
}

int keystore_get_addr_path(const keystore_t * key, const uint32_t * derivation, size_t len, const network_t * network, char ** addr, int flag){
    struct ext_key * child = NULL;
    int res;
    res = bip32_key_from_parent_path_alloc(key->root, derivation, len, BIP32_FLAG_KEY_PRIVATE, &child);
    child->version = network->xprv;

    if(flag == KEYSTORE_BECH32_ADDRESS){
        res |= wally_bip32_key_to_addr_segwit(child, network->bech32, 0, addr);
    }else{
        res |= wally_bip32_key_to_address(child, WALLY_ADDRESS_TYPE_P2SH_P2WPKH, network->p2sh, addr);
    }
    bip32_key_free(child);
    if(res!=WALLY_OK){
        wally_free_string(*addr);
    }
    return res;
}

int keystore_get_addr(const keystore_t * key, const char * path, const network_t * network, char ** addr, int flag){
    size_t len = 0;
    uint32_t * derivation = parse_derivation(path, &len);
    if(derivation == NULL){
        return -1;
    }
    int res = keystore_get_addr_path(key, derivation, len, network, addr, flag);
    free(derivation);
    return res;
}

int wallet_get_scriptpubkey(const wallet_t * wallet, const uint32_t * derivation, size_t derlen, uint8_t * scriptpubkey, size_t scriptpubkey_len){
    if(wallet->val == 0){ // TODO: implement for p2wpkh!
        return -1;
    }
    if(scriptpubkey_len < 34){
        return -1;
    }
    char path[100];
    sprintf(path, "/internal/%s/%s/%d.wallet", wallet->keystore->fingerprint, wallet->network->name, wallet->val-1);
    FILE *f = fopen(path, "r");
    if(!f){
        printf("missing file\r\n");
        return -1;
    }
    int m; int n;
    fscanf(f, "name=%*[^\n]\ntype=%*s\nm=%d\nn=%d\n", &m, &n);
    char xpub[150];
    uint8_t * pubs = (uint8_t *)malloc(33*n);
    for(int i=0; i<n; i++){
        fscanf(f, "[%*[^]]]%s\n", xpub);
        struct ext_key * k;
        struct ext_key * k2;
        struct ext_key * temp;
        int res = bip32_key_from_base58_alloc(xpub, &k);
        if(res != 0){
            free(pubs);
            printf("cant parse key: %s\r\n", xpub);
            return -1;
        }
        if(derlen > 0){
            bip32_key_from_parent_alloc(k, derivation[0], BIP32_FLAG_KEY_PUBLIC | BIP32_FLAG_SKIP_HASH, &k2);
            temp = k; k = k2; k2 = temp; // swap
        }
        for(int j=1; j<derlen; j++){
            bip32_key_from_parent(k, derivation[j], BIP32_FLAG_KEY_PUBLIC | BIP32_FLAG_SKIP_HASH, k2);
            temp = k; k = k2; k2 = temp; // swap
        }
        memcpy(pubs+33*i, k->pub_key, 33);
        temp = NULL;
        bip32_key_free(k);
        if(derlen > 0){
            bip32_key_free(k2);
        }
    }
    size_t len = 34*n+3;
    uint8_t * script = (uint8_t *)malloc(len);
    size_t lenout = 0;
    wally_scriptpubkey_multisig_from_bytes(pubs, 33*n, m, 0, script, len, &lenout);
    free(pubs);

    scriptpubkey[0] = 0;
    scriptpubkey[1] = 32;
    wally_sha256(script, lenout, scriptpubkey+2, 32);
    free(script);

    return 0;
}

int keystore_check_psbt(const keystore_t * key, const network_t * network, const struct wally_psbt * psbt, wallet_t * wallet){
    // check inputs: at least one to sign
    uint8_t err = KEYSTORE_PSBTERR_CANNOT_SIGN;
    uint8_t h160[20];
    // binary fingerprint of the root
    wally_hash160(key->root->pub_key, sizeof(key->root->pub_key),
                  h160, sizeof(h160));
    // all inputs have to correpond to the same wallet
    int wallet_id = -1; // undetermined yet
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
        if(psbt->inputs[i].witness_utxo == NULL){ // we don't support legacy
            return KEYSTORE_PSBTERR_UNSUPPORTED_POLICY;
        }
        // now let's check which wallet it corresponds to
        size_t script_type;
        uint8_t * script = psbt->inputs[i].witness_utxo->script;
        size_t script_len = psbt->inputs[i].witness_utxo->script_len;

        int res = wally_scriptpubkey_get_type(
                            script, 
                            script_len,
                            &script_type);
        if(res != WALLY_OK){
            return KEYSTORE_PSBTERR_UNSUPPORTED_POLICY;
        }
        if(script_type == WALLY_SCRIPT_TYPE_P2SH){
            if(psbt->inputs[i].redeem_script == NULL){
                return KEYSTORE_PSBTERR_WRONG_FIELDS;
            }
            script = psbt->inputs[i].redeem_script;
            script_len = psbt->inputs[i].redeem_script_len;
            res = wally_scriptpubkey_get_type(
                            script, 
                            script_len,
                            &script_type);
            if(res != WALLY_OK){
                return KEYSTORE_PSBTERR_WRONG_FIELDS;
            }
        }
        switch(script_type){
            case WALLY_SCRIPT_TYPE_P2WPKH:
            {
                // check that key is indeed the right one
                struct ext_key * pk;
                bip32_key_from_parent_path_alloc(key->root, 
                    psbt->inputs[i].keypaths->items[0].origin.path, 
                    psbt->inputs[i].keypaths->items[0].origin.path_len, 
                    BIP32_FLAG_KEY_PRIVATE, &pk);
                uint8_t h160[20];
                wally_hash160(pk->pub_key, 33, h160, 20);
                bip32_key_free(pk);
                if(memcmp(h160, script+2, 20) != 0){
                    return KEYSTORE_PSBTERR_WRONG_FIELDS;
                }
                if(wallet_id > 0){ // multisig and single are mixed
                    return KEYSTORE_PSBTERR_MIXED_INPUTS;
                }
                if(wallet_id < 0){
                    wallet_id = 0;
                }
                break;
            }
            case WALLY_SCRIPT_TYPE_P2WSH: // multisig
            {
                // find non-hardened derivation
                uint32_t * derivation = psbt->inputs[i].keypaths->items[0].origin.path;
                size_t derlen = psbt->inputs[i].keypaths->items[0].origin.path_len;
                while(derivation[0] >= BIP32_INITIAL_HARDENED_CHILD){
                    derivation = derivation+1;
                    derlen -= 1;
                }
                if(wallet_id == 0){
                    return KEYSTORE_PSBTERR_MIXED_INPUTS;
                }
                wallet_t w;
                uint8_t script2[34];
                if(wallet_id > 0){ // if wallet is already determined
                    keystore_get_wallet(key, network, wallet_id, &w);
                    wallet_get_scriptpubkey(&w, derivation, derlen, script2, sizeof(script2));
                    if(memcmp(script, script2, script_len) != 0){
                        return KEYSTORE_PSBTERR_MIXED_INPUTS;
                    }
                }else{ // search for matching wallet
                    int count = keystore_get_wallets_number(key, network);
                    for(int i=0; i<count; i++){
                        keystore_get_wallet(key, network, i+1, &w);
                        wallet_get_scriptpubkey(&w, derivation, derlen, script2, sizeof(script2));
                        if(memcmp(script, script2, script_len) == 0){
                            wallet_id = i+1;
                            break;
                        }
                    }
                }
                break;
            }
            default:
                printf("unknown\r\n");
                return KEYSTORE_PSBTERR_UNSUPPORTED_POLICY;
        }
    }
    if(wallet_id < 0){
        return KEYSTORE_PSBTERR_CANNOT_SIGN;
    }
    if((err == 0) && (wallet != NULL)){
        keystore_get_wallet(key, network, wallet_id, wallet);
    }
    return err;
}

int wallet_output_is_change(const wallet_t * wallet, const struct wally_psbt * psbt, uint8_t i, char ** warning){
    const keystore_t * key = wallet->keystore;
    // TODO: check if it is a change
    if(i >= psbt->num_outputs){
        return 0;
    }
    if(psbt->outputs[i].keypaths == NULL){
        return 0;
    }
    if(wallet->val > 0){ // multisig
        uint32_t * derivation = psbt->outputs[i].keypaths->items[0].origin.path;
        size_t derlen = psbt->outputs[i].keypaths->items[0].origin.path_len;
        while(derivation[0] >= BIP32_INITIAL_HARDENED_CHILD){
            derivation = derivation+1;
            derlen -= 1;
        }
        uint8_t scriptpubkey[34];
        wallet_get_scriptpubkey(wallet, derivation, derlen, scriptpubkey, sizeof(scriptpubkey));
        if(memcmp(scriptpubkey, psbt->tx->outputs[i].script, psbt->tx->outputs[i].script_len) == 0){
            return 1;
        }
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

int wallet_sign_psbt(const wallet_t * wallet, struct wally_psbt * psbt, char ** output){
    const keystore_t * key = wallet->keystore;
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
        int k = -1;
        uint8_t h160[20];
        wally_hash160(key->root->pub_key, sizeof(key->root->pub_key),
                  h160, sizeof(h160));
        for(int j = 0; j<psbt->inputs[i].keypaths->num_items; j++){
            if(memcmp(h160,psbt->inputs[i].keypaths->items[j].origin.fingerprint, 4) == 0){
                k = j;
                break;
            }
        }
        if(k < 0){
            return -1;
        }
        bip32_key_from_parent_path_alloc(key->root, 
            psbt->inputs[i].keypaths->items[k].origin.path, 
            psbt->inputs[i].keypaths->items[k].origin.path_len, 
            BIP32_FLAG_KEY_PRIVATE, &pk);

        if(wallet->val == 0){ // single key
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
        }else{
            if(psbt->inputs[i].witness_script == NULL){
                return -1;
            }
            wally_tx_get_btc_signature_hash(psbt->tx, i, 
                    psbt->inputs[i].witness_script, 
                    psbt->inputs[i].witness_script_len,
                    psbt->inputs[i].witness_utxo->satoshi,
                    WALLY_SIGHASH_ALL,
                    WALLY_TX_FLAG_USE_WITNESS,
                    hash, 32
                );
        }
 
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


// maybe expose it to public interface
int keystore_get_wallets_number(const keystore_t * key, const network_t * network){
    char path[100];
    sprintf(path, "/internal/%s", key->fingerprint);
    storage_maybe_mkdir(path);
    sprintf(path, "/internal/%s/%s", key->fingerprint, network->name);
    storage_maybe_mkdir(path);
                              // folder, extension
    return storage_get_file_count(path, ".wallet");
}

static int keystore_get_wallet_name(const keystore_t * key, const network_t * network, int i, char ** wname){
    char path[100];
    sprintf(path, "/internal/%s/%s/%d.wallet", key->fingerprint, network->name, i);
    FILE *f = fopen(path, "r");
    if(!f){
        return -1;
    }
    char w[100] = "Undefined";
    int m; int n;
    fscanf(f, "name=%[^\n]\ntype=%*s\nm=%d\nn=%d", w, &m, &n);
    sprintf(w+strlen(w), " (%d of %d)", m, n);
    *wname = (char *)malloc(strlen(w)+1);
    strcpy(*wname, w);
    return strlen(wname);
}

int keystore_get_wallets(const keystore_t * key, const network_t * network, char *** wallets){
    int num_wallets = keystore_get_wallets_number(key, network);
    if(num_wallets < 0){ // error
        return num_wallets;
    }
    char ** w = (char **)calloc(num_wallets+2, sizeof(char *));
    // first - default single key wallet
    w[0] = (char *)calloc(30, sizeof(char));
    sprintf(w[0], "Default (single key)");
    // multisig wallets:
    for(int i=1; i<num_wallets+1; i++){
        keystore_get_wallet_name(key, network, i-1, &w[i]);
    }
    // last - empty string
    w[num_wallets+1] = (char *)calloc(1, sizeof(char));
    *wallets = w;
    return num_wallets;
}

int keystore_free_wallets(char ** wallets){
    int i=0;
    if(wallets == NULL){
        return -1;
    }
    while(wallets[i] != NULL && strlen(wallets[i]) > 0){ // free everything that is not empty
        free(wallets[i]);
        i++;
    }
    free(wallets[i]); // last one
    free(wallets); // free the list
    wallets = NULL;
    return 0;
}

int keystore_get_wallet(const keystore_t * key, const network_t * network, int val, wallet_t * wallet){
    wallet->val = val;
    wallet->keystore = key;
    wallet->network = network;
    wallet->address = 0;
    if(val == 0){
        sprintf(wallet->name, "Default (single key)");
    }else{
        char * wname;
        keystore_get_wallet_name(key, network, val-1, &wname);
        strcpy(wallet->name, wname);
        free(wname);
    }
    return 0;
}

int wallet_get_addresses(const wallet_t * wallet, char ** base58_addr, char ** bech32_addr){
    if(wallet->val == 0){ // single key
        char path[50];
        sprintf(path, "m/84h/%dh/0h/0/%d", wallet->network->bip32, wallet->address);
        keystore_get_addr(wallet->keystore, path, wallet->network, bech32_addr, KEYSTORE_BECH32_ADDRESS);
        keystore_get_addr(wallet->keystore, path, wallet->network, base58_addr, KEYSTORE_BASE58_ADDRESS);
    }else{
        uint8_t scriptpubkey[34];
        uint32_t derivation[2] = {0, wallet->address};
        wallet_get_scriptpubkey(wallet, derivation, 2, scriptpubkey, sizeof(scriptpubkey));
        wally_addr_segwit_from_bytes(scriptpubkey, sizeof(scriptpubkey), wallet->network->bech32, 0, bech32_addr);
        uint8_t bytes[21];
        bytes[0] = wallet->network->p2sh;
        wally_hash160(scriptpubkey, sizeof(scriptpubkey), bytes+1, 20);
        wally_base58_from_bytes(bytes, 21, BASE58_FLAG_CHECKSUM, base58_addr);
    }
    return 0;
}

int keystore_check_wallet(const keystore_t * keystore, const network_t * network, const char * buf){
    // FIXME: hardcoded lengths are bad...
    char name[100];
    char type[10];
    int m;
    int n;
    char * rest;
    rest = (char *)calloc(strlen(buf)+1, 1);
    int res = sscanf(buf, "name=%[^\n]\ntype=%[^\n]\nm=%d\nn=%d\n%[^\0]", name, type, &m, &n, rest);
    if(res < 5){
        return KEYSTORE_WALLET_ERR_PARSING;
    }
    char derivation[150];
    char xpub[150];
    char * line = rest;
    int err = KEYSTORE_WALLET_ERR_NOT_INCLUDED;
    for(int i=0; i<n; i++){
        res = sscanf(line, "[%[^]]]%s", derivation, xpub);
        if(res < 2){
            line = NULL;
            free(rest);
            return KEYSTORE_WALLET_ERR_PARSING;
        }
        if(memcmp(derivation, keystore->fingerprint, 8) == 0){
            char * mypub;
            char * myslippub;
            res = keystore_get_xpub(keystore, derivation+9, network, 0, &mypub);
            res = keystore_get_xpub(keystore, derivation+9, network, 1, &myslippub);
            if(res < 0){
                free(rest);
                return KEYSTORE_WALLET_ERR_WRONG_XPUB;
            }
            if((strcmp(mypub, xpub) == 0) || (strcmp(myslippub, xpub)==0)){
                wally_free_string(mypub);
                wally_free_string(myslippub);
                err = 0;
            }else{
                wally_free_string(mypub);
                wally_free_string(myslippub);
                free(rest);
                return KEYSTORE_WALLET_ERR_WRONG_XPUB;
            }
        }
        line += strlen(derivation)+strlen(xpub)+3;
    }
    free(rest);
    return err;
}

int keystore_add_wallet(const keystore_t * keystore, const network_t * network, const char * buf, wallet_t * wallet){
    char path[100];
    sprintf(path, "/internal/%s", keystore->fingerprint);
    storage_maybe_mkdir(path);
    sprintf(path, "/internal/%s/%s", keystore->fingerprint, network->name);
    storage_maybe_mkdir(path);
                // folder, data, extension
    return storage_push(path, buf, ".wallet");
}

int keystore_verify_address(const keystore_t * keystore,
        const network_t * network,
        const char * addr,
        const uint32_t * path,
        size_t path_len,
        char ** wallet_name){
    // first we need to determine if address belongs to the network
    uint8_t * buf = (uint8_t *)malloc(strlen(addr));
    size_t len;
    int res = wally_base58_to_bytes(addr, BASE58_FLAG_CHECKSUM, buf, strlen(addr), &len);
    uint8_t prefix = buf[0];
    free(buf);
    int flag = KEYSTORE_BASE58_ADDRESS;
    if(res!=WALLY_OK){ // invalid base58 - probably bech32 address
        if(memcmp(addr, network->bech32, strlen(network->bech32)) != 0){ // wrong network
            return KEYSTORE_ERR_WRONG_NETWORK;
        }
        flag = KEYSTORE_BECH32_ADDRESS;
    }else{
        if(prefix != network->p2sh){
            return KEYSTORE_ERR_WRONG_NETWORK;
        }
    }
    // now let's check default wallet
    char * myaddr;
    uint32_t * derivation = (uint32_t *)calloc(path_len+3, sizeof(uint32_t));
    for(int i=0; i<path_len; i++){
        derivation[3+i] = path[i];
    }
    derivation[0] = BIP32_INITIAL_HARDENED_CHILD+84;
    derivation[1] = BIP32_INITIAL_HARDENED_CHILD+network->bip32;
    derivation[2] = BIP32_INITIAL_HARDENED_CHILD;
    res = keystore_get_addr_path(keystore, derivation, path_len+3, network, &myaddr, flag);
    free(derivation);
    if(strcmp(myaddr, addr) == 0){
        *wallet_name = (char *)calloc(30, sizeof(char));
        sprintf(*wallet_name, "Default (single key)");
        return 0;
    }
    // go through all multisig wallets
    wallet_t w;
    int count = keystore_get_wallets_number(keystore, network);
    for(int i=0; i<count; i++){
        keystore_get_wallet(keystore, network, i+1, &w);
        char * base58_addr;
        char * bech32_addr;
        // TODO: refactor using full path
        w.address = path[path_len-1];
        wallet_get_addresses(&w, &base58_addr, &bech32_addr);
        int mine = 0;
        if((strcmp(bech32_addr, addr) == 0) || (strcmp(base58_addr, addr) == 0)){
            mine = 1;
        }
        wally_free_string(base58_addr);
        wally_free_string(bech32_addr);
        if(mine){
            keystore_get_wallet_name(keystore, network, i, wallet_name);
            return 0;
        }
    }
    return KEYSTORE_ERR_NOT_MINE;
}
