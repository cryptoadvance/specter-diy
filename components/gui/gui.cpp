#include "mbed.h"
#include "helpers.h"
#include "gui.h"
#include "gui_common.h"
#include <string>

#include "tft.h"
#include "touchpad.h"
#include "lvgl.h"

#include "tpcal.h"
#include "alert.h"
#include "mnemonic.h"

#define BASE_UNDEFINED          0
#define BASE_INIT_SCREEN        1
#define BASE_RECOVERY_SCREEN    2
#define BASE_MNEMONIC_SCREEN    3
#define BASE_PASSWORD_SCREEN    4
#define BASE_MAIN_SCREEN        5
#define BASE_NETWORKS_SCREEN    6
#define BASE_XPUBS_SCREEN       7
#define BASE_PSBT_CONFIRMATION  8
#define BASE_RECKLESS           9
#define BASE_LIST_WALLETS       10
#define BASE_ADDRESSES_SCREEN   11
#define BASE_CONFIRM_NEW_WALLET 12

#define BACK_TO_MAIN            0xFF
#define GET_NEW_WALLET          0xFE

using std::string;

/* timer to count time in a loop and update the lvgl */
static volatile int t = 0;
Ticker ms_tick;
static void onMillisecondTicker(void){
    t++;
}

static int base = BASE_UNDEFINED;
static char input_buffer[501] = "";

static int action = GUI_NO_ACTION;
static int value = 0;
static char str[251] = "";

static uint8_t network_index;
static const char ** network_names;
static string default_xpubs[2];

lv_style_t title_style;

// main screen that we redraw
// alerts and prompts are on top of it
static lv_obj_t * scr;

static void gui_styles_create(){
    lv_style_copy(&title_style, &lv_style_plain);
    title_style.text.font = &lv_font_roboto_28;
}
static void cb(lv_obj_t * obj, lv_event_t event);
static void back_to_main(void * ptr);
static void back_to_init(void * ptr);

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

static void show_recovery_screen();

static void process_init_screen(int val){
    switch(val){
        case 1:
            action = GUI_GENERATE_KEY;
            break;
        case 2:
            show_recovery_screen();
            break;
        case 3:
            action = GUI_LOAD_MNEMONIC;
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
    lv_obj_t * obj;

    obj = gui_title_create(scr, "Pick master key to show:");

    uint16_t y = 100;
    string msg;
    msg = string("Single: ") + default_xpubs[0];
    obj = gui_button_create(scr, msg.c_str(), cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 1);
    y+=100;

    msg = string("Multisig: ") + default_xpubs[1];
    obj = gui_button_create(scr, msg.c_str(), cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 2);
    y+=100;

    // TODO: add "scan custom derivation" button

    obj = gui_button_create(scr, "Back to main menu", cb);
    lv_obj_set_user_data(obj, BACK_TO_MAIN);
}

void gui_navigate_wallet(const char * name, uint32_t address, const char * bech32_addr, const char * base58_addr){
    base = BASE_ADDRESSES_SCREEN;

    string qrmsg = "bitcoin:";
    qrmsg += bech32_addr;
    string msg = bech32_addr;
    msg += "\nor base58:\n";
    msg += base58_addr;

    char title[200];
    sprintf(title, "Wallet \"%s\"\nAddress #%d", name, address+1);

    lv_obj_clean(scr);
    lv_obj_t * obj;

    obj = gui_title_create(scr, title);
    lv_obj_t * qr = gui_qr_create(scr, LV_HOR_RES/2, qrmsg.c_str());
    lv_obj_set_y(qr, lv_obj_get_y(obj) + lv_obj_get_height(obj) + PADDING);

    obj = gui_title_create(scr, msg.c_str(), true);
    lv_obj_set_y(obj, lv_obj_get_y(qr) + lv_obj_get_height(qr) + PADDING);

    obj = gui_button_create(scr, "Previous", cb);
    uint16_t y = lv_obj_get_y(obj) - 100;
    lv_obj_set_user_data(obj, address-1);
    lv_obj_set_y(obj, y);
    lv_obj_set_width(obj, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(obj, PADDING);
    if(address == 0){
        lv_btn_set_state(obj, LV_BTN_STATE_INA);
    }

    obj = gui_button_create(scr, "Next", cb);
    lv_obj_set_user_data(obj, address+1);
    lv_obj_set_y(obj, y);
    lv_obj_set_width(obj, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(obj, LV_HOR_RES/2+PADDING/2);

    obj = gui_button_create(scr, "Back to main menu", cb);
    lv_obj_set_user_data(obj, BACK_TO_MAIN);
}


static void show_reckless_screen(){
    base = BASE_RECKLESS;

    lv_obj_clean(scr);
    lv_obj_t * obj;

    obj = gui_title_create(scr, "Careful with that!");

    uint16_t y = 100;
    obj = gui_button_create(scr, "Save recovery phrase", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 1);
    y+=100;

    obj = gui_button_create(scr, "Delete recovery phrase", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 2);
    y+=100;

    obj = gui_button_create(scr, "Show recovery phrase", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 3);
    y+=100;

    obj = gui_button_create(scr, "Back to main screen", cb);
    lv_obj_set_user_data(obj, BACK_TO_MAIN);
}

static void process_main_screen(int val){
    switch(val){
        case 1: // multisig
            action = GUI_LIST_WALLETS;
            logit("gui", "action set to list wallets");
            break;
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
        case 7:
            show_reckless_screen();
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
    if(val == BACK_TO_MAIN){
        lv_async_call(back_to_main, NULL);
        memset(input_buffer, 0, sizeof(input_buffer));
        return;
    }
    switch(base){
        case BASE_RECKLESS:
            switch(val){
                case 1:
                    action = GUI_SAVE_MNEMONIC;
                    break;
                case 2:
                    action = GUI_DELETE_MNEMONIC;
                    break;
                case 3:
                    action = GUI_SHOW_MNEMONIC;
                    break;
            }
            break;
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
                strcpy(str, default_xpubs[value].c_str());
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
            }else{
                gui_show_main_screen();
            }
            break;
        case BASE_LIST_WALLETS:
            if(val == GET_NEW_WALLET){
                action = GUI_NEW_WALLET;
            }else{
                value = val;
                action = GUI_SELECT_WALLET;
            }
            break;
        case BASE_CONFIRM_NEW_WALLET:
            if(val == 1){
                action = GUI_CONFIRM_NEW_WALLET;
            }else{
                action = GUI_CANCEL_NEW_WALLET;
            }
            break;
        case BASE_ADDRESSES_SCREEN:
            value = val;
            action = GUI_GET_WALLET_ADDRESS;
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

void gui_confirm_new_wallet(const char * wallet_info){
    base = BASE_CONFIRM_NEW_WALLET;
    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "Add new wallet?");

    obj = gui_title_create(scr, wallet_info, 1);
    lv_obj_set_y(obj, 100);

    obj = gui_button_create(scr, "Confirm", cb);
    lv_obj_set_user_data(obj, 1);
    lv_obj_set_width(obj, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(obj, LV_HOR_RES/2+PADDING/2);

    obj = gui_button_create(scr, "Cancel", cb);
    lv_obj_set_user_data(obj, 0);
    lv_obj_set_width(obj, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(obj, PADDING);
}

void gui_show_wallets(char ** wallets){
    base = BASE_LIST_WALLETS;
    if(wallets==NULL){
        show_err("Weird... You don't have any wallets");
        return;
    }
    lv_obj_clean(scr);
    lv_obj_t * obj;

    obj = gui_title_create(scr, "Your wallets:");

    uint16_t y = 100;
    int i=0;
    while(wallets[i]!=NULL && strlen(wallets[i]) > 0){
        obj = gui_button_create(scr, wallets[i], cb);
        lv_obj_set_user_data(obj, i);
        lv_obj_set_y(obj, y);
        i++;
        y += 100;
    }

    obj = gui_button_create(scr, "Add new wallet (scan)", cb);
    lv_obj_set_user_data(obj, GET_NEW_WALLET);
    lv_obj_set_y(obj, lv_obj_get_y(obj)-100);

    obj = gui_button_create(scr, "Back to main menu", cb);
    lv_obj_set_user_data(obj, BACK_TO_MAIN);
}

void gui_show_signed_psbt(const char * output){
    gui_show_main_screen();
    gui_qr_alert_create("Transaction is signed!", output, "Scan it with your wallet", "Back to main screen");
}

void gui_show_psbt(uint64_t out_amount, uint64_t change_amount, uint64_t fee, uint8_t num_outputs, txout_t * outputs){
    base = BASE_PSBT_CONFIRMATION;

    lv_obj_clean(scr);

    lv_obj_t * obj;
    char msg[200];
    sprintf(msg, "Confirm transaction:\nSpending %llu satoshi", out_amount-change_amount+fee);
    obj = gui_title_create(scr, msg);

    uint16_t y = 100;
    sprintf(msg, "Number of outputs: %u\n"
                 "Fee: %llu satoshi\n"
                 "Outputs:\n"
               , num_outputs
               , fee
               );
    obj = gui_title_create(scr, msg, true);
    lv_obj_set_y(obj, y);
    y+=100;
    for(int i=0; i<num_outputs; i++){
        // TODO: display warnings if any
        if(outputs[i].is_change){
            sprintf(msg, "%s (change): %llu sat\n", outputs[i].address, outputs[i].amount);
        }else{
            sprintf(msg, "%s: %llu sat\n", outputs[i].address, outputs[i].amount);
        }
        obj = gui_title_create(scr, msg, true);
        lv_obj_set_y(obj, y);
        y+=100;
    }

    obj = gui_button_create(scr, "Confirm", cb);
    lv_obj_set_user_data(obj, 1);
    lv_obj_set_width(obj, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(obj, LV_HOR_RES/2+PADDING/2);

    obj = gui_button_create(scr, "Cancel", cb);
    lv_obj_set_user_data(obj, 2);
    lv_obj_set_width(obj, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(obj, PADDING);
}

void gui_show_xpub(const char * fingerprint, const char * derivation, const char * xpub){

    if(memcmp(derivation, "m/", 2)==0){
        derivation = derivation+2;
    }
    string msg = string("[")+string(fingerprint)+string("/")+string(derivation)+string("]")+xpub;
    gui_qr_alert_create("Your master key:", msg.c_str(), msg.c_str(), "Ok");
}

void gui_show_init_screen(){
    base = BASE_INIT_SCREEN;

    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "What do you want to do?");

    uint16_t y = 100;
    obj = gui_button_create(scr, "Generate new key", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 1);
    y+=100;

    obj = gui_button_create(scr, "Enter recovery phrase", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 2);
    y+=100;

    obj = gui_button_create(scr, "Load key from memory", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 3);
    y+=100;
}

/********************** mnemonic screen ********************/

static lv_obj_t * tbl;

void gui_show_reckless_mnemonic(const char * mnemonic){

    gui_alert_create("Your recovery phrase", "", "Ok");

    lv_obj_t * alert_scr = lv_disp_get_scr_act(NULL);

    lv_obj_t * obj = gui_mnemonic_table_create(alert_scr, mnemonic);
}

void gui_show_mnemonic(const char * mnemonic){
    base = BASE_MNEMONIC_SCREEN;
    value = 12;

    lv_obj_clean(scr);
    lv_obj_t * obj;
    obj = gui_title_create(scr, "Write down your recovery phrase");

    tbl = gui_mnemonic_table_create(scr, mnemonic);

    uint16_t y = lv_obj_get_y(tbl)+lv_obj_get_height(tbl)+30;
    obj = gui_title_create(scr, "Regenerate with number of words:", true);
    lv_obj_set_y(obj, y);

    y+=60;
    char btntext[10];
    uint16_t pad2 = 5; 
    for(int i=0; i<5; i++){
        sprintf(btntext, "%d", 12+i*3);
        obj = gui_button_create(scr, btntext, cb);
        lv_obj_set_user_data(obj, i+2);
        lv_obj_set_width(obj, (LV_HOR_RES-2*PADDING)/5-pad2);
        lv_obj_set_x(obj, (LV_HOR_RES-2*PADDING+pad2)*i/5+PADDING);
        lv_obj_set_y(obj, y);
    }

    obj = gui_button_create(scr, "Back", cb);
    lv_obj_set_user_data(obj, 1);
    lv_obj_set_width(obj, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(obj, PADDING);

    obj = gui_button_create(scr, "Continue", cb);
    lv_obj_set_user_data(obj, 7);
    lv_obj_set_width(obj, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(obj, LV_HOR_RES/2+PADDING/2);
}

static const char * keymap[] = {"Q","W","E","R","T","Y","U","I","O","P","\n",
                          "A","S","D","F","G","H","J","K","L","\n",
                          "Z","X","C","V","B","N","M","<","\n",
                          "Back","Next word","Done",""};

static void cb_keyboard(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        const char * txt = lv_btnm_get_active_btn_text(obj);
        uint16_t id = lv_btnm_get_active_btn(obj);
        if(lv_btnm_get_btn_ctrl(obj, id, LV_BTNM_CTRL_INACTIVE)){
            return;
        }
        if(strcmp(txt, "Next word")==0){
            input_buffer[strlen(input_buffer)] = ' ';
        }else if(strcmp(txt, "<")==0){
            if(strlen(input_buffer) > 0){
                input_buffer[strlen(input_buffer)-1] = 0;
            }
        }else if(strcmp(txt, "Back")==0){
            memset(input_buffer, 0, sizeof(input_buffer));
            lv_async_call(back_to_init, NULL);
        }else if(strcmp(txt, "Done")==0){
            process_command(0);
        }else{
            input_buffer[strlen(input_buffer)] = tolower(txt[0]);
        }
        gui_show_mnemonic(tbl, input_buffer, true);
        gui_check_mnemonic(input_buffer, obj);
    }
}

static void show_recovery_screen(){
    base = BASE_RECOVERY_SCREEN;

    lv_obj_clean(scr);

    lv_obj_t * obj;
    obj = gui_title_create(scr, "Enter your recovery phrase:");

    tbl = gui_mnemonic_table_create(scr, input_buffer);

    // keyboard
    lv_obj_t * kb = lv_kb_create(scr, NULL);
    lv_obj_set_y(kb, LV_VER_RES*2/3);
    lv_obj_set_height(kb, LV_VER_RES/3);
    lv_kb_set_map(kb, keymap);

    static lv_style_t kb_dis_style;
    lv_style_copy(&kb_dis_style, &lv_style_btn_ina);
    kb_dis_style.body.main_color = LV_COLOR_MAKE(0xe0,0xe0,0xe0);
    kb_dis_style.body.grad_color = LV_COLOR_MAKE(0xe0,0xe0,0xe0);
    kb_dis_style.body.radius = 0;
    kb_dis_style.body.border.opa = 30;
    lv_kb_set_style(kb, LV_KB_STYLE_BTN_INA, &kb_dis_style);

    lv_obj_set_event_cb(kb, cb_keyboard);
    lv_btnm_set_btn_ctrl(kb, 29, LV_BTNM_CTRL_INACTIVE);
    lv_btnm_set_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
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

    /* Create a text area. The keyboard will write here */
    lv_obj_t * ta = lv_ta_create(scr, NULL);
    lv_obj_set_size(ta, LV_HOR_RES-2*PADDING, 150);
    lv_ta_set_text(ta, "");
    // lv_ta_set_pwd_mode(ta, true); // password mode... tricky
    lv_obj_align(ta, NULL, LV_ALIGN_IN_TOP_MID, 0, 200);
    lv_obj_set_style(ta, &lv_style_transp);

    /* Assign the text area to the keyboard */
    lv_kb_set_ta(kb, ta);
}

/********************** main screen ********************/

void gui_show_main_screen(){
    base = BASE_MAIN_SCREEN;

    lv_obj_clean(scr);
    lv_obj_t * obj;

    obj = gui_title_create(scr, "Select an option below");

    uint16_t y = 100;

    obj = gui_button_create(scr, "Wallets", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 1);
    y+=100;
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
    obj = gui_button_create(scr, "# Reckless", cb);
    lv_obj_set_y(obj, y);
    lv_obj_set_user_data(obj, 7);
    y+=100;

    // TODO: add GUI_SECURE_SHUTDOWN
    // TODO: add Advanced menu:
    //       - Reckless save mnemonic
    //       - SD card support
}

static void back_to_main(void * ptr){
    gui_show_main_screen();
}

static void back_to_init(void * ptr){
    gui_show_init_screen();
}

void gui_set_default_xpubs(const char * single, const char * multisig){
    default_xpubs[0] = single;
    default_xpubs[1] = multisig;
}

void gui_show_addresses(const char * derivation, const char * bech32_addr, const char * base58_addr){
    string qrmsg = "bitcoin:";
    qrmsg += bech32_addr;
    string msg = "bech32: ";
    msg += bech32_addr;
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
