/**
 * DISCLAIMER
 * This is our "functional prototype", this means that even though
 * it is kinda functional, there are plenty of security holes and bugs.
 * That's why you are not able to store your private keys here - 
 * only public information. And you should NOT trust this wallet
 * Use it carefully, on the testnet, otherwise you could lose your funds.
 *
 * Also architecture and the whole codebase will be refactored significantly
 * in the future and we are not maintaining backwards compatibility.
 */

#include "mbed.h"
#include "rng.h"
#include "storage.h"
#include "gui.h"
#include "host.h"
#include "Bitcoin.h"
#include "tpcal.h"
#include "main.h"
#include "PSBT.h"
#include "Electrum.h"

int maybe_create_default_wallet();

Serial pc(SERIAL_TX, SERIAL_RX, 115200);
DigitalIn btn(USER_BUTTON);

HDPrivateKey root;
PrivateKey id_key;
const Network * network = &Testnet;
char storage_path[100] = "";
PSBT psbt;
ElectrumTx etx;

wallet_t wallet;

static std::string temp_data;

void update(){
    gui_update();
    host_update();
	if(btn){
        while(btn){
            wait(0.1);
        }
        gui_calibrate();
	}
}

void cb_err(int err){
    gui_alert_create("Error", "Scanning QR code failed - timout?\n\nTry again.", "OK");
}

void set_network(int net){
	string fingerprint = root.fingerprint();
	switch(net){
		case 1:
			network = &Mainnet;
		    sprintf(storage_path, "/internal/%s/mainnet/", fingerprint.c_str());
		    maybe_create_default_wallet();
			gui_alert_create("Selected Main network", "Be careful plz", "OK");
			break;
		case 2:
			network = &Testnet;
		    sprintf(storage_path, "/internal/%s/testnet/", fingerprint.c_str());
		    maybe_create_default_wallet();
			gui_alert_create("Selected Test network", "Coins worth nothing here", "OK");
			break;
		case 3:
			network = &Regtest;
		    sprintf(storage_path, "/internal/%s/regtest/", fingerprint.c_str());
		    maybe_create_default_wallet();
			gui_alert_create("Selected Regtest", "I suppose you know what you are doing", "OK");
			break;
		default:
			network = &Testnet;
		    sprintf(storage_path, "/internal/%s/testnet/", fingerprint.c_str());
		    maybe_create_default_wallet();
			gui_alert_create("Error", "Wrong network. Switched back to Testnet.", "OK");
	}
}

void show_key(int type){
	char msg[200];
	HDPublicKey pub;
	switch(type){
		case 1: // segwit
			pub = root.hardenedChild(84).hardenedChild(network->bip32).hardenedChild(0).xpub();
			sprintf(msg,"[%s/84h/%dh/0h]%s", root.fingerprint().c_str(), network->bip32, pub.toString().c_str());
			break;
		case 2: // nested
			pub = root.hardenedChild(49).hardenedChild(network->bip32).hardenedChild(0).xpub();
			sprintf(msg,"[%s/49h/%dh/0h]%s", root.fingerprint().c_str(), network->bip32, pub.toString().c_str());
			break;
		case 3: // legacy
			pub = root.hardenedChild(44).hardenedChild(network->bip32).hardenedChild(0).xpub();
			sprintf(msg,"[%s/44h/%dh/0h]%s", root.fingerprint().c_str(), network->bip32, pub.toString().c_str());
			break;
		case 4: // segwit
			pub = root.hardenedChild(48).hardenedChild(network->bip32).hardenedChild(0).hardenedChild(2).xpub();
			sprintf(msg,"[%s/48h/%dh/0h/2h]%s", root.fingerprint().c_str(), network->bip32, pub.toString().c_str());
			break;
		case 5: // nested
			pub = root.hardenedChild(48).hardenedChild(network->bip32).hardenedChild(0).hardenedChild(1).xpub();
			sprintf(msg,"[%s/48h/%dh/0h/1h]%s", root.fingerprint().c_str(), network->bip32, pub.toString().c_str());
			break;
		case 6: // legacy
			pub = root.hardenedChild(45).xpub();
			pub.network = network;
			sprintf(msg,"[%s/45h]%s", root.fingerprint().c_str(), pub.toString().c_str());
			break;
		default:
			gui_alert_create("Error", "Wrong network. Switched back to Testnet.", "OK");
			return;
	}
	gui_qr_alert_create("Master key", msg, msg, "OK");
}

void add_cosigner_confirmed(void * ptr){
    gui_main_menu_show(NULL);
    gui_alert_create("Sorry", "Not implemented yet", "OK");
}

void add_cosigner(const char * data){
    gui_prompt_create("Add new cosigner key?", data, "OK", add_cosigner_confirmed, "Cancel", gui_main_menu_show);
}

void request_new_cosigner(void * ptr){
    host_request_data(add_cosigner, cb_err);
}

void sign_etx(void * ptr){
    etx.sign(root.hardenedChild(49).hardenedChild(network->bip32).hardenedChild(0));
    uint8_t * raw = new uint8_t[etx.length()];
    size_t len = etx.serialize(raw, etx.length());
    string b43 = toBase43(raw, len);
    gui_main_menu_show(NULL); // screen to go back to
    gui_qr_alert_create("Signed transaction", b43.c_str(), "Scan it", "OK");
}

void sign_psbt(void * ptr){
    psbt.sign(root);
    uint8_t * raw = new uint8_t[psbt.length()];
    size_t len = psbt.serialize(raw, psbt.length());
    string b64 = toBase64(raw, len);
    gui_main_menu_show(NULL); // screen to go back to
    gui_qr_alert_create("Signed transaction", b64.c_str(), "Scan it", "OK");
}

void show_etx(){
    char title[30];
    string msg = "Sending to:\n\n";
    string change = "";
    float send_amount = 0;
    HDPublicKey xpub = root.hardenedChild(49).hardenedChild(network->bip32).hardenedChild(0).xpub().child(1);
    for(int i=0; i<etx.tx.outputsNumber; i++){
        // electrum doesn't provide derivation information for change, we need to bruteforce
        // TODO: store a range of change addresses to help bruteforce while we don't have PSBT plugin
        bool is_change = false;
        string addr = etx.tx.txOuts[i].address(network);
        for(int j=0; j<20; j++){ // 20 addresses for now
            PublicKey pub = xpub.child(j);
            if(pub.nestedSegwitAddress(network) == addr){
                is_change = true;
                break;
            }
        }
        if(!is_change){
            send_amount += etx.tx.txOuts[i].btcAmount();
            msg += addr;
            char s[20];
            sprintf(s, ": %.8f BTC\n\n", etx.tx.txOuts[i].btcAmount());
            msg += s;
        }else{
            if(change.length() == 0){
                change = "Change outputs:\n\n";
            }
            change += addr;
            char s[20];
            sprintf(s, ": %.8f BTC\n\n", etx.tx.txOuts[i].btcAmount());
            change += s;
        }
    }
    char s[100];
    sprintf(s, "Fee: %.8f BTC (%.2f percent)", float(etx.fee())/1e8, float(etx.fee())/1e8/send_amount*100);
    msg += change;
    msg += s;
    send_amount += float(etx.fee())/1e8;
    sprintf(title, "Sending %.8f BTC\nfrom <Wallet name>", send_amount);
    gui_prompt_create(title, msg.c_str(), "Sign", sign_etx, "Cancel", gui_main_menu_show);
}


void show_psbt(){
    char title[30];
    string msg = "Sending to:\n\n";
    string change = "";
    float send_amount = 0;
    for(int i=0; i<psbt.tx.outputsNumber; i++){
        if(!psbt.isMine(i, root)){
            send_amount += psbt.tx.txOuts[i].btcAmount();
            msg += psbt.tx.txOuts[i].address(network);
            char s[20];
            sprintf(s, ": %.8f BTC\n\n", psbt.tx.txOuts[i].btcAmount());
            msg += s;
        }else{
            if(change.length() == 0){
                change = "Change outputs:\n\n";
            }
            change += psbt.tx.txOuts[i].address(network);
            char s[20];
            sprintf(s, ": %.8f BTC\n\n", psbt.tx.txOuts[i].btcAmount());
            change += s;
        }
    }
    char s[100];
    sprintf(s, "Fee: %.8f BTC (%.2f percent)", float(psbt.fee())/1e8, float(psbt.fee())/1e8/send_amount*100);
    msg += change;
    msg += s;
    send_amount += float(psbt.fee())/1e8;
    sprintf(title, "Sending %.8f BTC\nfrom <Wallet name>", send_amount);
    gui_prompt_create(title, msg.c_str(), "Sign", sign_psbt, "Cancel", gui_main_menu_show);
}

void parse_etx(const char * data){
    uint8_t * raw = new uint8_t[strlen(data)*3/4];
    size_t len = fromBase43(data, strlen(data), raw, strlen(data)*3/4);
    if(len > 0){
        etx.reset();
        len = etx.parse(raw, len);
    }
    delete [] raw;
    if(len <= 0){
        gui_alert_create("Parsing error", "Failed to parse transaction", "OK");
        return;
    }
    show_etx();
}

void parse_psbt(const char * data){
    uint8_t * raw = new uint8_t[strlen(data)*3/4];
    size_t len = fromBase64(data, strlen(data), raw, strlen(data)*3/4);
    if(len > 0){
        psbt.reset();
        len = psbt.parse(raw, len);
    }
    delete [] raw;
    if(len <= 0){
        gui_alert_create("Parsing error", "Failed to parse transaction", "OK");
        return;
    }
    show_psbt();
}

void get_psbt(void * ptr){
    host_request_data(parse_psbt, cb_err);
}

void get_etx(void * ptr){
    host_request_data(parse_etx, cb_err);
}

int create_dir(const char * path){
	int err = 0;
    DIR *d = opendir(path);
    if(!d){
        err = mkdir(path, 0777);
        if(err != 0){
            return -2;
        }
    }else{
	    closedir(d);
    }
    return 0;
}

int maybe_create_default_wallet(){
	char path[200] = "";
	sprintf(path, "%s/wallets", storage_path);
    if(create_dir(path) < 0){
        fs_err("Failed to create wallets folder");
        return -1;
    }
    // open default wallet file, their name is just an index
    sprintf(path+strlen(path), "/0");
    FILE *f = fopen(path, "r");
    if(!f){
    	// cant find file => create one
	    f = fopen(path, "w+");
	    if(!f){
    	    fs_err("Failed to write wallet file");
    	    return -1;
    	}
    	// fwrite(points, sizeof(lv_point_t), 4, f);
    	HDPublicKey pub = root.hardenedChild(49).hardenedChild(network->bip32).hardenedChild(0).xpub();
    	fprintf(f, "name=Default\ntype=P2SH_P2WPKH\naddress=0\n[%s/49h/%dh/0h]%s", 
    			root.fingerprint().c_str(), network->bip32, pub.toString().c_str()
    		);
    	// FIXME: add signature file (hmac / ecdsa) for integrity check
	    fclose(f);
    }else{
    	fclose(f);
    }
	return 0;
}

bool wallet_exists(int num){
	char path[200] = "";
	sprintf(path, "%s/wallets/%d", storage_path, num);
    FILE *f = fopen(path, "r");
    if(!f){
    	return false;
    }
	fclose(f);
	return true;
}

int get_derivation(const char * path, xpub_t * xpub){
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
            return -1;
        }
        if(cur[i] == '/'){
            derivationLen++;
        }
    }
    xpub->derivation_len = derivationLen;
    xpub->derivation = new uint32_t[derivationLen];
    size_t current = 0;
    xpub->derivation[current] = 0;
    for(size_t i=0; i<len; i++){
        if(cur[i] == '/'){ // next
            current++;
		    xpub->derivation[current] = 0;
            continue;
        }
        const char * pch = strchr(VALID_CHARS, cur[i]);
        uint32_t val = pch-VALID_CHARS;
        if(xpub->derivation[current] >= 0x80000000){ // can't have anything after hardened
            delete [] xpub->derivation;
        	xpub->derivation_len = 0;
        	xpub->derivation = NULL;
            return -2;
        }
        if(val < 10){
            xpub->derivation[current] = xpub->derivation[current]*10 + val;
        }else{ // h or ' -> hardened
            xpub->derivation[current] += 0x80000000;
        }
    }
    return 0;
}

int load_wallet(int num){
	// first clear loaded wallet
	if(wallet.xpubs_len > 0){
		for(int i=0; i<wallet.xpubs_len; i++){
			if(wallet.xpubs[i].derivation_len > 0){
				delete [] wallet.xpubs[i].derivation;
				wallet.xpubs[i].derivation = NULL;
				wallet.xpubs[i].derivation_len = 0;
			}
		}
		delete [] wallet.xpubs;
		wallet.xpubs = NULL;
		wallet.xpubs_len = 0;
	}
    wallet.address = 0;
	memset(wallet.name, 0, sizeof(wallet.name));

	// now load from file
	char path[200] = "";
	sprintf(path, "%s/wallets/%d", storage_path, num);
    FILE *f = fopen(path, "r");
    if(!f){
    	return -1;
    }
    fscanf(f, "name=%s\n", wallet.name);
    char type[10];
    fscanf(f, "type=%s\n", type);
    fscanf(f, "address=%u\n", &wallet.address);

    if(strcmp(type, "P2PKH") == 0){
    	wallet.type = P2PKH;
    	wallet.sigs_required = 1;
    	wallet.xpubs_len = 1;
    }
    if(strcmp(type, "P2WPKH") == 0){
    	wallet.type = P2WPKH;
    	wallet.sigs_required = 1;
    	wallet.xpubs_len = 1;
    }
    if(strcmp(type, "P2SH_P2WPKH") == 0){
    	wallet.type = P2SH_P2WPKH;
    	wallet.sigs_required = 1;
    	wallet.xpubs_len = 1;
    }
    if(strcmp(type, "P2SH") == 0){
    	wallet.type = P2SH;
    	fscanf(f, "m=%c\n", &wallet.sigs_required);
    	fscanf(f, "n=%c\n", &wallet.xpubs_len);
    }
    if(strcmp(type, "P2WSH") == 0){
    	wallet.type = P2WSH;
    	fscanf(f, "m=%c\n", &wallet.sigs_required);
    	fscanf(f, "n=%c\n", &wallet.xpubs_len);
    }
    if(strcmp(type, "P2SH_P2WSH") == 0){
    	wallet.type = P2SH_P2WSH;
    	fscanf(f, "m=%c\n", &wallet.sigs_required);
    	fscanf(f, "n=%c\n", &wallet.xpubs_len);
    }
    
    // wallet.xpubs = (xpub_t *)calloc(wallet.xpubs_len, sizeof(xpub_t));
    wallet.xpubs = new xpub_t[wallet.xpubs_len];
    for(int i=0; i<wallet.xpubs_len; i++){
    	char fingerprint[9] = "";
    	char der[100] = ""; // meh... TODO: refactor
    	char xpub[120] = ""; // 111 really
    	char line[240] = "";
    	if(i == wallet.xpubs_len-1){ // ugly
	    	fscanf(f, "[%s", line);
    	}else{
	    	fscanf(f, "[%s\n", line);
    	}
        memcpy(fingerprint, line, 8);
        char * pch = strchr(line, ']');
        size_t len = pch-line;
        memcpy(der, line+9, len-9);
        memcpy(xpub, pch+1, strlen(pch+1));

    	wallet.xpubs[i].xpub.fromString(xpub);
    	fromHex(fingerprint, 8, wallet.xpubs[i].fingerprint, 4);
    	get_derivation(der, &wallet.xpubs[i]);
    }
    // check that my key is there
    bool mine = false;
    for(int i=0; i<wallet.xpubs_len; i++){
    	uint8_t fingerprint[4];
    	root.fingerprint(fingerprint);
    	HDPublicKey pub;
    	if(memcmp(fingerprint, wallet.xpubs[i].fingerprint, 4) != 0){
    		continue;
    	}else{
    		pub = root.derive(wallet.xpubs[i].derivation, wallet.xpubs[i].derivation_len).xpub();
    		uint8_t xpub_arr[100] = { 0 }; // 87 actually, whatever
    		uint8_t xpub_arr2[100] = { 0 };
    		size_t len = pub.serialize(xpub_arr, 100);
    		wallet.xpubs[i].xpub.serialize(xpub_arr2, 100);
    		if(memcmp(xpub_arr+4, xpub_arr2+4, len-4)!=0){
    			gui_alert_create("Error", "Something is wrong with the master key", "OK");
    			return -2;
    		}else{
    			mine = true;
    			break;
    		}
    	}
    }
    if(!mine){
    	gui_alert_create("Error", "My key is not in the wallet", "OK");
    	return -3;
    }
    string address = "unsupported";
    printf("deriving from %s\r\n", wallet.xpubs[0].xpub.toString().c_str());
	printf("Network (%s)\r\n", wallet.xpubs[0].xpub.network->bech32);
	printf("child: %s\r\n", wallet.xpubs[0].xpub.child(0).child(wallet.address).toString().c_str());
	HDPublicKey child = wallet.xpubs[0].xpub.child(0).child(wallet.address);
    switch(wallet.type){
    	case P2PKH:
    		address = child.legacyAddress(child.network); // meh...
    		break;
    	case P2SH_P2WPKH:
    		address = child.nestedSegwitAddress(child.network);
    		break;
    	case P2WPKH:
    		address = child.segwitAddress(child.network);
    		break;
    	default:
    		address = "unsupported";
    }
    gui_qr_alert_create(wallet.name, (string("bitcoin:")+address).c_str(), address.c_str(), "OK");
	return 0;
}
void check_address(const char * data){
    char address[100];
    char type[10];
    char derivation[100];
    sscanf(data, "address=%s\ntype=%s\n%s", address, type, derivation);

    string fingerprint = root.fingerprint();
    if(memcmp(fingerprint.c_str(), derivation, 8) != 0){
        gui_alert_create("Error", "Wrong fingerprint in derivation", "OK");
        return;
    }
    HDPublicKey xpub = root.derive(derivation+9).derive(address).xpub();
    if(!xpub.isValid()){
        gui_alert_create("Error", "Wrong derivation", "OK");
        return;
    }
    PublicKey pub = xpub;
    string addr = "unsupported";
    if(strcmp(type, "P2PKH") == 0){
        addr = pub.legacyAddress(network);
    }
    if(strcmp(type, "P2WPKH") == 0){
        addr = pub.segwitAddress(network);
    }
    if(strcmp(type, "P2SH_P2WPKH") == 0){
        addr = pub.nestedSegwitAddress(network);
    }
    // gui_alert_create("Your address", s.c_str(), "OK");
    gui_qr_alert_create("Your address", (string("bitcoin:")+addr).c_str(), addr.c_str(), "OK");
}

void verify_address(void * ptr){
    host_request_data(check_address, cb_err);
}

int get_wallets_number(){
	int i=0;
	while(wallet_exists(i)){
		i++;
	}
	return i;
}

const char * get_wallet_name(int num){
	char path[200] = "";
	sprintf(path, "%s/wallets/%d", storage_path, num);
    FILE *f = fopen(path, "r");
    if(!f){
    	return NULL;
    }
    static char buf[100]; // omg, TODO: rewrite securely
    fscanf(f, "name=%s\n", buf);
    static char type[10];
    fscanf(f, "type=%s\n", type);
    if(strcmp(type, "P2PKH") == 0){
    	sprintf(buf + strlen(buf), " (Legacy)");
    }
    if(strcmp(type, "P2WPKH") == 0){
    	sprintf(buf + strlen(buf), " (Native Segwit)");
    }
    if(strcmp(type, "P2SH_P2WPKH") == 0){
    	sprintf(buf + strlen(buf), " (Nested Segwit)");
    }
    if(strcmp(type, "P2SH") == 0){
    	sprintf(buf + strlen(buf), " (Multisig Legacy)");
    }
    if(strcmp(type, "P2WSH") == 0){
    	sprintf(buf + strlen(buf), " (Multisig Native Segwit)");
    }
    if(strcmp(type, "P2SH_P2WSH") == 0){
    	sprintf(buf + strlen(buf), " (Multisig Nested Segwit)");
    }
	fclose(f);
	return buf;
}

bool cosigner_exists(int num){
	char path[200] = "";
	sprintf(path, "%s/cosigners/%d", storage_path, num);
    FILE *f = fopen(path, "r");
    if(!f){
    	return false;
    }
	fclose(f);
	return true;
}

int get_cosigners_number(){
	char path[200] = "";
	sprintf(path, "%s/cosigners", storage_path);
	create_dir(path);
	int i=0;
	while(cosigner_exists(i)){
		i++;
	}
	return i;
}

const char * get_cosigner_name(int num){
	char path[200] = "";
	sprintf(path, "%s/cosigners/%d", storage_path, num);
    FILE *f = fopen(path, "r");
    if(!f){
    	return NULL;
    }
    static char buf[100]; // omg, TODO: rewrite securely
    fscanf(f, "name=%s\n", buf);
	fclose(f);
	return buf;
}

int check_storage(){
    // check if settings file is in the internal storage
    DIR *d = opendir("/internal/");
    if(!d){
        fs_err("Can't open internal storage");
        return -1;
    }
    closedir(d);
    string fingerprint = root.fingerprint();
    char path[200] = "";
    sprintf(path, "/internal/%s", fingerprint.c_str());
    if(create_dir(path) < 0){
        fs_err("Failed to create internal storage folder");
        return -2;
    }
    sprintf(path, "/internal/%s/testnet", fingerprint.c_str());
    if(create_dir(path) < 0){
        fs_err("Failed to create internal storage folder");
        return -3;
    }
    sprintf(path, "/internal/%s/mainnet", fingerprint.c_str());
    if(create_dir(path) < 0){
        fs_err("Failed to create internal storage folder");
        return -4;
    }
    sprintf(path, "/internal/%s/regtest", fingerprint.c_str());
    if(create_dir(path) < 0){
        fs_err("Failed to create internal storage folder");
        return -5;
    }
    sprintf(storage_path, "/internal/%s/testnet", fingerprint.c_str());
	int err = maybe_create_default_wallet();
    return err;
}

void init_keys(const char * mnemonic, const char * password){
	root.fromMnemonic(mnemonic, password);
	if(!root.isValid()){
		gui_init_menu_show(NULL); // a screen to return to
		gui_alert_create("Wrong key", "Key derivation didn't work", "OK");
		return;
	}
	id_key = root.hardenedChild(0x1D); // used to authenticate data in storage
	int err = check_storage();
	if(err == 0){
		err = maybe_create_default_wallet();
	}
	if(err == 0){
		gui_main_menu_show(NULL);
	}
}

/* TODO:
 * - refactor storage
 * - get rid of unsecure functions like fscanf
 * - add hmac on wallet files to check integrity
 */
int main(){
	// just in case
	wallet.xpubs = NULL;
	wallet.xpubs_len = 0;
	memset(wallet.name, 0, sizeof(wallet.name));

    rng_init();        // random number generator
	storage_init();    // on-board memory & sd card
					   // on-board memory is on external chip => untrusted
	host_init();       // communication - functions to scan & display qr codes 
	 				   //                 and talke to sd card storage
    gui_init();   	   // display functions

    gui_start();	   // start the gui

    // for testing, pre-defined mnemonic
    // init_keys("also panda decline code guard palace spread squirrel stereo sudden fee noodle", "test");
    // gui_set_mnemonic("also panda decline code guard palace spread squirrel stereo sudden fee noodle");

    while(1){
    	update();
    }
}
