#include "mbed.h"
#include "helpers.h"
#include "gui.h"
#include "gui_common.h"

#include "tft.h"
#include "touchpad.h"
#include "lvgl.h"

#include "tpcal.h"
#include "alert.h"

#define BASE_UNDEFINED          0
#define BASE_INIT_SCREEN        1
#define BASE_RECOVERY_SCREEN    2
#define BASE_MNEMONIC_SCREEN    3
#define BASE_PASSWORD_SCREEN    4
#define BASE_MAIN_SCREEN        5
#define BASE_NETWORKS_SCREEN    6
#define BASE_XPUBS_SCREEN       7
#define BASE_PSBT_CONFIRMATION  8

using std::string;

/* timer to count time in a loop and update the lvgl */
static volatile int t = 0;
Ticker ms_tick;
static void onMillisecondTicker(void){
    t++;
}

static int base = BASE_UNDEFINED;
static char input_buffer[501] = "";

static struct timeval tmo;
static fd_set readfds;

static int action = GUI_NO_ACTION;
static int value = 0;
static char str[251] = "";

static uint8_t network_index;
static const char ** network_names;
static char default_xpubs[2][20];

lv_style_t title_style;

// main screen that we redraw
// alerts and prompts are on top of it
static lv_obj_t * scr;

static void gui_styles_create(){
    lv_style_copy(&title_style, &lv_style_plain);
    title_style.text.font = &lv_font_roboto_28;
}
static void cb(lv_obj_t * obj, lv_event_t event);

int gui_get_action(){
    return action;
}
int gui_get_value(){
    return value;
}
char * gui_get_str(){
    return str;
}

void gui_clear_action(){
    action = GUI_NO_ACTION;
}

void gui_set_network(uint8_t index){
    network_index = index;
}

void gui_set_available_networks(const char * names[]){
    network_names = names;
}

void gui_start(){
    gui_show_init_screen();
}

/***************** calibration stuff ****************/

void hang(){
    while(true){ // just stop operating
        sleep();
    }
}

void fs_err(const char * msg){
    static const char * errormsg;
    if(msg!=NULL){ // if null - shows last message
        errormsg = msg;
    }
    gui_alert_create("File system error", errormsg, NULL);
}

// FIXME: move most of this stuff to storage
int gui_calibration_load(){
    int err = 0;

    // check if settings file is in the internal storage
    DIR *d = opendir("/internal/");
    if(!d){
        fs_err("Can't open internal storage");
        return -1;
    }
    closedir(d);
    d = opendir("/internal/gui/");
    if(!d){
        err = mkdir("/internal/gui", 0777);
        if(err != 0){
            fs_err("Failed to create gui folder");
            return -2;
        }
    }
    closedir(d);
    // check if we need to calibrate the screen
    FILE *f = fopen("/internal/gui/calibration", "r");
    if(!f){
        fs_err("Calibration file is missing...");
        return -3;
    }
    lv_point_t points[4];
    fread(points, sizeof(lv_point_t), 4, f);
    touchpad_calibrate(points);
    fclose(f);
    return err;
}

void gui_calibration_save(lv_point_t * points){

    FILE *f = fopen("/internal/gui/calibration", "w");
    if(!f){
        fs_err("Failed to write calibration file");
        return;
    }
    fwrite(points, sizeof(lv_point_t), 4, f);
    fclose(f);

    touchpad_calibrate(points);

    gui_alert_create("Done.\nNow, let's make it clear.",
        "This wallet doesn't store your private keys, "
        "this means you need to use your recovery phrase "
        "every time you want to sign a transaction.\n\n"
        "It only stores some metadata like "
        "master public keys, cosigners, wallets configuration etc.\n\n"
        "You can wipe the device when you want - "
        "it will zero all persistent memory.\n\n"
        "You should be aware that this is an experimental project, "
        "so better use it on testnet or in multisig "
        "with some other hardware wallet."
        , "Ok, I understand");

}

/*************** init stuff ***************/

void gui_init(){
    lv_init();
    tft_init();
    touchpad_init();
    ms_tick.attach_us(onMillisecondTicker, 1000);

    /* define theme */
    lv_theme_t * th = lv_theme_material_init(210, NULL);
    lv_theme_set_current(th);

    gui_styles_create();

    // create screen
    scr = lv_cont_create(NULL, NULL);
    lv_disp_load_scr(scr);

    /* loading calibration file */
    int err = gui_calibration_load();
    if(err < 0){
        logit("gui", "calibration required");
        // if file is not found
        if(err == -3){
            /* calibration screen and a callback when done */
            tpcal_create(gui_calibration_save);
        }
    }

}

void gui_update(){
    HAL_Delay(1);
    lv_tick_inc(t);
    lv_task_handler();
    t = 0;
}

/****************** screens & logic **************/

static void show_recovery_screen(){
    base = BASE_RECOVERY_SCREEN;
    // printf("Enter your recovery phrase:\r\n");
    lv_obj_clean(scr);

}

static void process_init_screen(int val){
    switch(val){
        case 1:
            action = GUI_GENERATE_KEY;
            break;
        case 2:
            show_recovery_screen();
            break;
    }
}

static void process_mnemonic_screen(int val){
    switch(val){
        case 1: // go back
            gui_show_init_screen();
            break;
        case 7: // continue -> enter recovery phrase to check
            show_recovery_screen();
            break;
        default: // re-generate 12-word key
            value = 12;
            if(val > 1 && val < 7){
                value += (val-2)*3;
            }
            action = GUI_GENERATE_KEY;
            break;
    }
}

static void show_networks_screen(){
    base = BASE_NETWORKS_SCREEN;

    lv_obj_clean(scr);
    lv_obj_t * obj;

    obj = gui_title_create(scr, "Pick the network to use:");

    uint16_t y = 100;
    int i = 0;
    const char * net = network_names[i];
    while(strlen(net) > 0){
        obj = gui_button_create(scr, net, cb);
        lv_obj_set_y(obj, y);
        lv_obj_set_user_data(obj, i+1);
        y+=100;
        i++;
        net = network_names[i];
    }
}

static void show_xpubs_screen(){
    base = BASE_XPUBS_SCREEN;

    lv_obj_clean(scr);

    // printf("\r\nPick xpub to show:\r\n"
    //            "[1] Single: %s\r\n"
    //            "[2] Multisig: %s\r\n"
    //            "[3] Back\r\n", default_xpubs[0], default_xpubs[1]
    //     );
}

static void process_main_screen(int val){
    switch(val){
        case 2: // master keys
            show_xpubs_screen();
            break;
        case 3:
            action = GUI_SIGN_PSBT;
            logit("gui", "action set to Sign PSBT");
            break;
        case 4:
            action = GUI_VERIFY_ADDRESS;
            logit("gui", "action set to Verify address");
            break;
        case 5: // use another passwd
            gui_get_password();
            break;
        case 6: // pick network
            show_networks_screen();
            break;
    }
}

static int copy_string(){
    if(strlen(input_buffer) > sizeof(str)-1){
        show_err("Input is too large, try again.");
        return 0;
    }
    strcpy(str, input_buffer);
    return 1;
}

static void process_command(int val){
    // if(strcmp(input_buffer, "q") == 0){
    //     action = GUI_SECURE_SHUTDOWN;
    //     memset(input_buffer, 0, sizeof(input_buffer));
    //     return;
    // }
    // int val = 0;
    switch(base){
        case BASE_INIT_SCREEN:
            process_init_screen(val);
            break;
        case BASE_MNEMONIC_SCREEN:
            process_mnemonic_screen(val);
            break;
        case BASE_RECOVERY_SCREEN:
            if(copy_string()){
                action = GUI_PROCESS_MNEMONIC;
            }
            break;
        case BASE_PASSWORD_SCREEN:
            if(val == 1){
                action = GUI_BACK;
            }else{
                if(copy_string()){
                    action = GUI_PROCESS_PASSWORD;
                }
            }
            break;
        case BASE_MAIN_SCREEN:
            process_main_screen(val);
            break;
        case BASE_NETWORKS_SCREEN:
            value = val-1;
            action = GUI_PROCESS_NETWORK;
            break;
        case BASE_XPUBS_SCREEN:
            if(val >= 1 && val < 3){
                value = val-1;
                strcpy(str, default_xpubs[value]);
                action = GUI_SHOW_XPUB;
            }
            if(val == 3){
                gui_show_main_screen();
            }
            break;
        case BASE_PSBT_CONFIRMATION:
            if(val == 1){
                action = GUI_PSBT_CONFIRMED;
                printf("\r\nOk, signing transaction\r\n");
            }
            break;
        default:
            show_err("Undefined GUI behaviour");
    }
    memset(input_buffer, 0, sizeof(input_buffer));
}

static void cb(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        int v = lv_obj_get_user_data(obj);
        process_command(v);
    }
}

void gui_show_psbt(uint64_t out_amount, uint64_t change_amount, uint64_t fee, uint8_t num_outputs, txout_t * outputs){
    base = BASE_PSBT_CONFIRMATION;

    lv_obj_clean(scr);

    // printf("\r\nConfirm transaction:\r\n"
    //            "Spending %llu satoshi\r\n"
    //            "Number of outputs: %u\r\n"
    //            "Fee: %llu satoshi\r\n"
    //            "Outputs:\r\n"
    //            , out_amount - change_amount + fee
    //            , num_outputs
    //            , fee
    //            );
    // for(int i=0; i<num_outputs; i++){
    //     printf("%d: %s: %llu sat\r\n", i+1, outputs[i].address, outputs[i].amount);
    // }
    // printf("[1] Confirm\r\n"
    //        "[2] Cancel\r\n");
}

void gui_show_xpub(const char * fingerprint, const char * derivation, const char * xpub){
    // if(memcmp(derivation, "m/", 2)==0){
    //     derivation = derivation+2;
    // }
    // printf("\r\nYour xpub:\r\n"
    //             ">>> \033[1m[%s/%s]%s\033[0m <<<\r\n", fingerprint, derivation, xpub);
    // show_xpubs_screen();
}

void gui_show_init_screen(){
    base = BASE_INIT_SCREEN;

    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "What do you want to do?");

    obj = gui_button_create(scr, "Generate new key", cb);
    lv_obj_set_y(obj, 200);
    lv_obj_set_user_data(obj, 1);

    obj = gui_button_create(scr, "Enter recovery phrase", cb);
    lv_obj_set_y(obj, 300);
    lv_obj_set_user_data(obj, 2);
}

void gui_show_mnemonic(const char * mnemonic){
    base = BASE_MNEMONIC_SCREEN;
    value = 12;

    lv_obj_clean(scr);

    // printf("\r\nYour recovery phrase:\r\n"
    //        ">>> \033[1m%s\033[0m <<<\r\n", mnemonic);
    // printf("What's next?\r\n"
    //        "[1] Back to init screen\r\n"
    //        "[2] Generate a 12-word mnemonic\r\n"
    //        "[3] Generate a 15-word mnemonic\r\n"
    //        "[4] Generate a 18-word mnemonic\r\n"
    //        "[5] Generate a 21-word mnemonic\r\n"
    //        "[6] Generate a 24-word mnemonic\r\n"
    //        "[7] Continue\r\n"
    //     );
}

/********************** password screen ********************/

// keyboard config
static const char * pkeymapCap[] = {
                          "Q","W","E","R","T","Y","U","I","O","P","\n",
                          "#@","A","S","D","F","G","H","J","K","L","\n",
                          "^ ","Z","X","C","V","B","N","M","<-","\n",
                          "Clear"," ","Done",""};
static const char * pkeymapLow[] = {
                          "q","w","e","r","t","y","u","i","o","p","\n",
                          "#@","a","s","d","f","g","h","j","k","l","\n",
                          "^  ","z","x","c","v","b","n","m","<-","\n",
                          "Clear"," ","Done",""};
static const char * pkeymapNum[] = {
                          "1","2","3","4","5","6","7","8","9","0","\n",
                          "aA","@","#","$","_","&","-","+","(",")","/","\n",
                          "[","]","*","\"","'",":",";","!","?","\\","<-","\n",
                          "Clear"," ","Done",""};

// key press callback
static void cb_pkeyboard(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_CLICKED){
        const char * txt = lv_btnm_get_active_btn_text(obj);
        if(strcmp(txt, "<-")==0){
            if(strlen(input_buffer) > 0){
                input_buffer[strlen(input_buffer)-1] = 0;
            }
        }else if(strcmp(txt, "Clear")==0){
            memset(input_buffer, 0, sizeof(input_buffer));
        }else if(strcmp(txt, "Done")==0){
            process_command(0);
        }else if(strcmp(txt,"^  ")==0){
            lv_kb_set_map(obj, pkeymapCap);
        }else if(strcmp(txt,"^ ")==0){
            lv_kb_set_map(obj, pkeymapLow);
        }else if(strcmp(txt,"#@")==0){
            lv_kb_set_map(obj, pkeymapNum);
        }else if(strcmp(txt,"aA")==0){
            lv_kb_set_map(obj, pkeymapLow);
        }else{
            input_buffer[strlen(input_buffer)] = txt[0];
        }
        lv_obj_t * ta = lv_kb_get_ta(obj);
        lv_ta_set_text(ta, input_buffer);
    }
}

void gui_get_password(){
    base = BASE_PASSWORD_SCREEN;

    lv_obj_clean(scr);

    gui_title_create(scr, "Enter your password (optional)");

    // keyboard
    lv_obj_t * kb = lv_kb_create(scr, NULL);
    lv_obj_set_y(kb, LV_VER_RES*2/3);
    lv_obj_set_height(kb, LV_VER_RES*1/3);
    lv_kb_set_map(kb, pkeymapLow);
    lv_obj_set_event_cb(kb, cb_pkeyboard);

    /*Create a text area. The keyboard will write here*/
    lv_obj_t * ta = lv_ta_create(scr, NULL);
    lv_obj_set_size(ta, LV_HOR_RES-2*PADDING, 150);
    lv_ta_set_text(ta, "");
    // lv_ta_set_pwd_mode(ta, true); // password mode... tricky
    lv_obj_align(ta, NULL, LV_ALIGN_IN_TOP_MID, 0, 200);
    lv_obj_set_style(ta, &lv_style_transp);

    /*Assign the text area to the keyboard*/
    lv_kb_set_ta(kb, ta);
}

/********************** main screen ********************/

void gui_show_main_screen(){
    base = BASE_MAIN_SCREEN;

    lv_obj_clean(scr);
    lv_obj_t * obj;

    obj = gui_title_create(scr, "Select an option below");

    uint16_t y = 100;
    // obj = gui_button_create(scr, "Wallets", cb_list_wallets);
    // lv_obj_set_y(obj, y);
    // y+=100;
    obj = gui_button_create(scr, "Master keys", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 2);
    y+=100;
    obj = gui_button_create(scr, "Sign transaction", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 3);
    y+=100;
    obj = gui_button_create(scr, "Verify address", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 4);
    y+=100;
    obj = gui_button_create(scr, "Use another password", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 5);
    y+=100;
    obj = gui_button_create(scr, "Switch network", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 6);
    y+=100;
}

void gui_set_default_xpubs(const char * single, const char * multisig){
    // fixme: check lengths
    strcpy(default_xpubs[0], single);
    strcpy(default_xpubs[1], multisig);
}

void gui_show_addresses(const char * derivation, const char * segwit_addr, const char * base58_addr){
    // why not to use strings?
    string qrmsg = "bitcoin:";
    qrmsg += segwit_addr;
    string msg = "bech32: ";
    msg += segwit_addr;
    msg += "\nbase58: ";
    msg += base58_addr;

    gui_qr_alert_create("Your bitcoin address", qrmsg.c_str(), msg.c_str(), "Ok");
}

void gui_calibrate(){
    lv_point_t points[4];
    points[0].x = 0;
    points[0].y = 0;
    points[1].x = TFT_HOR_RES;
    points[1].y = 0;
    points[2].x = TFT_HOR_RES;
    points[2].y = TFT_VER_RES;
    points[3].x = 0;
    points[3].y = TFT_VER_RES;
    touchpad_calibrate(points);
    tpcal_create(gui_calibration_save);
}

#if 0

#include "gui.h"
#include "mbed.h"
#include "tft.h"
#include "touchpad.h"
#include "host.h"
#include "gui_common.h"
#include "./tpcal/tpcal.h"
#include "./alert/alert.h"
#include "./mnemonic/mnemonic.h"
#include "Bitcoin.h"

/* timer to count time in a loop and update the lvgl */
static volatile int t = 0;
Ticker ms_tick;
static void onMillisecondTicker(void){
  t++;
}

lv_obj_t * txt; // label

lv_style_t title_style;
// static lv_style_t list__style;
// static lv_style_t gray_style;
// static lv_style_t kb_dis_style;

lv_obj_t * gui_alert(const char * title, const char * message, void (*callback)(lv_obj_t * btn, lv_event_t event));
void gui_keys_menu_show(void * ptr);
void gui_network_selector_show(void * ptr);
void gui_wallets_menu_show(void * ptr);
void gui_cosigners_menu_show(void * ptr);

static void gui_styles_create(){
    lv_style_copy(&title_style, &lv_style_plain);
    title_style.text.font = &lv_font_roboto_28;
}

void cb_init(lv_obj_t * btn, lv_event_t event){
    lv_label_set_text(txt,"");
}

void cb_data_ready(const char * buffer){
    lv_label_set_text(txt, buffer);
}

void cb_scan(lv_obj_t * btn, lv_event_t event){
    // int res = qrscanner.scan(qrbuf, sizeof(qrbuf));
    lv_label_set_text(txt, "Scanning...");
    host_request_data(cb_data_ready);
}

static void cb_enter_mnemonic(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_mnemonic_enter_show, NULL);
    }
}

static void cb_new_mnemonic(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_mnemonic_new_show, NULL);
    }
}

static void cb_not_imeplemnted(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        gui_alert_create("Error", "Not implemented, sorry", "Ok");
    }
}

static void cb_list_wallets(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_wallets_menu_show, NULL);
    }
}

static void cb_list_cosigners(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_cosigners_menu_show, NULL);
    }
}

static void cb_master_keys(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        // gui_qr_alert_create("Error", "Not implemented", "Not implemented, sorry", "Ok");
        lv_async_call(gui_keys_menu_show, NULL);
    }
}

static void cb_switch_network(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_network_selector_show, NULL);
    }
}

static void cb_set_network(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_main_menu_show, lv_scr_act());
        set_network(lv_obj_get_user_data(obj));
    }
}

static void cb_show_key(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        // lv_async_call(gui_main_menu_show, lv_scr_act());
        show_key(lv_obj_get_user_data(obj));
    }
}

static void cb_to_main_menu(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_main_menu_show, lv_scr_act());
    }
}

static void cb_set_password(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_password_enter_show, lv_scr_act());
    }    
}

static void cb_load_wallet(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        int num = lv_obj_get_user_data(obj);
        int err = load_wallet(num);
        if(err != 0){
            return;
        }
    }    
}

static void cb_add_cosigner(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(request_new_cosigner, NULL);
    }    
}

void gui_wallets_menu_show(void * ptr){
    lv_obj_t * scr;
    if(ptr == NULL){
        scr = lv_scr_act();
    }else{
        scr = (lv_obj_t*)ptr;
    }
    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "Select the wallet");
    uint16_t y = 100;

    int count = get_wallets_number();
    for(int i=0; i<count; i++){
        obj = gui_button_create(scr, get_wallet_name(i), cb_load_wallet);
        lv_obj_set_y(obj, y);
        lv_obj_set_user_data(obj, i);
        y+=100;
    }

    obj = gui_button_create(scr, "Add new wallet (scan)", cb_not_imeplemnted);
    lv_obj_set_y(obj, lv_obj_get_y(obj)-100);
    obj = gui_button_create(scr, "Back", cb_to_main_menu);
}

void gui_cosigners_menu_show(void * ptr){
    lv_obj_t * scr;
    if(ptr == NULL){
        scr = lv_scr_act();
    }else{
        scr = (lv_obj_t*)ptr;
    }
    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "List of known cosigners");
    uint16_t y = 100;

    int count = get_cosigners_number();
    for(int i=0; i<count; i++){
        obj = gui_button_create(scr, get_cosigner_name(i), cb_not_imeplemnted);
        lv_obj_set_y(obj, y);
        lv_obj_set_user_data(obj, i);
        y+=100;
    }

    obj = gui_button_create(scr, "Add new cosigner (scan)", cb_add_cosigner);
    lv_obj_set_y(obj, lv_obj_get_y(obj)-100);
    obj = gui_button_create(scr, "Back", cb_to_main_menu);
}

void gui_network_selector_show(void * ptr){
    lv_obj_t * scr;
    if(ptr == NULL){
        scr = lv_scr_act();
    }else{
        scr = (lv_obj_t*)ptr;
    }
    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "Select the network");
    uint16_t y = 100;
    obj = gui_button_create(scr, "Mainnet", cb_set_network);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 1);
    y+=100;
    obj = gui_button_create(scr, "Testnet", cb_set_network);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 2);
    y+=100;
    obj = gui_button_create(scr, "Regtest", cb_set_network);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 3);
    y+=100;

    obj = gui_button_create(scr, "Back", cb_to_main_menu);
}

static void cb_more_keys(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_obj_set_hidden(obj, true); // hide button
        lv_obj_t * scr = lv_scr_act();
        // add more buttons
        uint16_t y = 300;
        obj = gui_button_create(scr, "Single - Segwit", cb_show_key);
        lv_obj_set_y(obj, y);
        lv_obj_set_user_data(obj, 1);
        y+=100;
        obj = gui_button_create(scr, "Single - Legacy", cb_show_key);
        lv_obj_set_y(obj, y);
        lv_obj_set_user_data(obj, 3);
        y+=100;
        obj = gui_button_create(scr, "Multisig - Segwit", cb_show_key);
        lv_obj_set_y(obj, y);
        lv_obj_set_user_data(obj, 4);
        y+=100;
        obj = gui_button_create(scr, "Multisig - Legacy", cb_show_key);
        lv_obj_set_y(obj, y);
        lv_obj_set_user_data(obj, 6);
        y+=100;
    }
}

static void cb_get_psbt(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(get_psbt, NULL);
    }
}

static void cb_scan_address(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(verify_address, NULL);
    }
}

void gui_keys_menu_show(void * ptr){
    lv_obj_t * scr;
    if(ptr == NULL){
        scr = lv_scr_act();
    }else{
        scr = (lv_obj_t*)ptr;
    }
    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "Select the key to display");

    uint16_t y = 100;
    obj = gui_button_create(scr, "Single (Nested Segwit)", cb_show_key);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 2);
    y+=100;
    obj = gui_button_create(scr, "Multisig (Nested Segwit)", cb_show_key);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 5);
    y+=100;
    obj = gui_button_create(scr, "Other keys", cb_more_keys);
    lv_obj_set_y(obj, y);
    y+=100;

    obj = gui_button_create(scr, "Back", cb_to_main_menu);
}

void gui_init_menu_show(void * ptr){
    lv_obj_t * scr;
    if(ptr == NULL){
        scr = lv_scr_act();
    }else{
        scr = (lv_obj_t*)ptr;
    }
    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "What do you want to do?");

    obj = gui_button_create(scr, "Generate new key", cb_new_mnemonic);
    lv_obj_set_y(obj, 200);
    obj = gui_button_create(scr, "Enter recovery phrase", cb_enter_mnemonic);
    lv_obj_set_y(obj, 300);
}

void gui_main_menu_show(void * ptr){
    lv_obj_t * scr;
    if(ptr == NULL){
        scr = lv_scr_act();
    }else{
        scr = (lv_obj_t*)ptr;
    }
    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "Select an option below");

    uint16_t y = 100;
    obj = gui_button_create(scr, "Wallets", cb_list_wallets);
    lv_obj_set_y(obj, y);
    y+=100;
    obj = gui_button_create(scr, "Master keys", cb_master_keys);
    lv_obj_set_y(obj, y);
    y+=100;
    obj = gui_button_create(scr, "Cosigners", cb_list_cosigners);
    lv_obj_set_y(obj, y);
    y+=100;
    obj = gui_button_create(scr, "Sign transaction", cb_get_psbt);
    lv_obj_set_y(obj, y);
    y+=100;
    obj = gui_button_create(scr, "Verify address", cb_scan_address);
    lv_obj_set_y(obj, y);
    y+=100;
    obj = gui_button_create(scr, "Use another password", cb_set_password);
    lv_obj_set_y(obj, y);
    y+=100;
    obj = gui_button_create(scr, "Switch network", cb_switch_network);
    lv_obj_set_y(obj, y);
    y+=100;

}

void gui_start(){
    /* create and load screen */
    lv_obj_t * scr = lv_cont_create(NULL, NULL);
    lv_disp_load_scr(scr);

    /* show init menu */
    gui_init_menu_show(scr);

    /* now when we've built the main screen
     * we can do preliminary steps */

    /* loading calibration file */
    int err = gui_calibration_load();
    if(err < 0){
        // if file is not found
        if(err == -3){
            /* calibration screen and a callback when done */
            tpcal_create(gui_calibration_save);
        }
    }
}

void gui_calibrate(){
    tpcal_create(gui_calibration_save);
}

#endif
