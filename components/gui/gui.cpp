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

void gui_init(){
    lv_init();
    tft_init();
    touchpad_init();
    ms_tick.attach_us(onMillisecondTicker, 1000);

    /* define theme */
    lv_theme_t * th = lv_theme_material_init(210, NULL);
    lv_theme_set_current(th);

    gui_styles_create();
}

void gui_update(){
    HAL_Delay(1);
    lv_tick_inc(t);
    lv_task_handler();
    t = 0;
}

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
    FILE *f = fopen("/internal/gui/calibraion", "r");
    if(!f){
        fs_err("Calibration file is missing...");
        return -3;
    }
    lv_point_t points[4];
    fread(points, sizeof(lv_point_t), 4, f);
    tounchpad_calibrate(points);
    fclose(f);
    return err;
}

void gui_calibration_save(lv_point_t * points){

    FILE *f = fopen("/internal/gui/calibraion", "w+");
    if(!f){
        fs_err("Failed to write calibration file");
    }
    fwrite(points, sizeof(lv_point_t), 4, f);
    fclose(f);

    gui_calibration_load();

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
