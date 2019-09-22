#if 0
#include "mnemonic.h"
#include "lvgl.h"
#include <stdio.h>
#include "../gui_common.h"
#include "../gui.h"
#include "Bitcoin.h"
#include "utility/trezor/bip39_english.h"
#include "rng.h"

static char mnemonic[256]="";
static char password[256]="";

static lv_obj_t * kb;
static lv_obj_t * table;
static lv_obj_t * ntable;
static lv_style_t kb_dis_style;

static lv_obj_t * gui_table_create(lv_obj_t * scr);
static void gui_show_mnemonic(lv_obj_t * tbl, bool check);

void gui_set_mnemonic(const char * mn){
    memset(mnemonic, 0, sizeof(mnemonic));
    memcpy(mnemonic, mn, strlen(mn));
}

static const char * keymap[] = {"Q","W","E","R","T","Y","U","I","O","P","\n",
                          "A","S","D","F","G","H","J","K","L","\n",
                          "Z","X","C","V","B","N","M","<","\n",
                          "Back","Next word","Done",""};

static uint8_t buf[32];

static void cb_back(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_init_menu_show, NULL);
    }
}

static void cb_enter(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        lv_async_call(gui_mnemonic_enter_show, NULL);
    }
}

static bool use24 = true;
static void cb_toggle24(lv_obj_t * obj, lv_event_t event){
    if(event==LV_EVENT_RELEASED){
        use24 = !use24;
        gui_mnemonic_new_show(NULL);
    }
}

void gui_mnemonic_new_show(void * ptr){
    lv_obj_t * scr;
    if(ptr == NULL){
        scr = lv_scr_act();
    }else{
        scr = (lv_obj_t*)ptr;
    }
    lv_obj_clean(scr);

    gui_title_create(scr, "Write down your recovery phrase");

    ntable = gui_table_create(scr);
    rng_get_random_buffer(buf, sizeof(buf));
    const char * m = generateMnemonic(buf, 16+16*use24); // 24 word mnemonic
    memset(mnemonic, 0, sizeof(mnemonic));
    memcpy(mnemonic, m, strlen(m));
    gui_show_mnemonic(ntable, false);

    lv_obj_t * btn;
    char msg[40];
    sprintf(msg, "Use %d words", 12*(1+!use24));
    btn = gui_button_create(scr, msg, cb_toggle24);
    lv_obj_set_y(btn, lv_obj_get_y(btn)-100);

    btn = gui_button_create(scr, "Back", cb_back);
    lv_obj_set_width(btn, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(btn, PADDING);

    btn = gui_button_create(scr, "Confirm", cb_enter);
    lv_obj_set_width(btn, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(btn, LV_HOR_RES/2+PADDING/2);
}

static void gui_show_mnemonic(lv_obj_t * tbl, bool check){
    printf("mne: %s\r\n", mnemonic);
    int cellnum = 0;
    int word_start = 0;
    char word[10] = "";
    for(unsigned i=0; i<strlen(mnemonic); i++){
        if(mnemonic[i]==' '){
            memset(word, 0, sizeof(word));
            memcpy(word, mnemonic + word_start, i - word_start);
            lv_table_set_cell_value(tbl, cellnum % 12, 1+2*(cellnum/12), word);
            cellnum++;
            word_start = i + 1;
        }
    }
    if(check){
        lv_table_set_cell_type(tbl, cellnum%12, 2*(cellnum/12), LV_TABLE_STYLE_CELL1);
    }
    if(cellnum>0){
        lv_table_set_cell_type(tbl, (cellnum-1)%12, 2*((cellnum-1)/12), LV_TABLE_STYLE_CELL2);
    }
    if(cellnum<24){
        lv_table_set_cell_type(tbl, (cellnum+1)%12, 2*((cellnum+1)/12), LV_TABLE_STYLE_CELL2);
    }
    // last word
    if((word_start < strlen(mnemonic))||(word_start==0)){
        lv_table_set_cell_value(tbl, cellnum % 12, 1+2*(cellnum/12), mnemonic + word_start);
    }
    int words = cellnum+1;
    if(words < 24){
        lv_table_set_cell_value(tbl, words % 12, 1+2*(words/12), "");
    }

    if(check){
        char * lastWord = mnemonic;
        for(int i=strlen(mnemonic)-1; i>=0; i--){
            if(mnemonic[i]==' '){
                lastWord = mnemonic+i+1;
                break;
            }
        }
        if(strlen(lastWord) > 0){
            bool correct = false;
            for(int i=0; i<2048; i++){
                if(strcmp(wordlist[i], lastWord) == 0){
                    correct = true;
                    break;
                }
            }
            if(correct){
                lv_btnm_clear_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
            }else{
                lv_btnm_set_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
            }
        }else{
            lv_btnm_set_btn_ctrl(kb, 29, LV_BTNM_CTRL_INACTIVE);
            lv_btnm_set_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
        }
        if(words == 24){
            lv_btnm_set_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
        }
        if(words==12 || words == 24){
            if(checkMnemonic(mnemonic)){
                lv_btnm_clear_btn_ctrl(kb, 29, LV_BTNM_CTRL_INACTIVE);
            }else{
                lv_btnm_set_btn_ctrl(kb, 29, LV_BTNM_CTRL_INACTIVE);
            }
        }
    }
}

static void cb_keyboard(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_RELEASED){
        const char * txt = lv_btnm_get_active_btn_text(obj);
        uint16_t id = lv_btnm_get_active_btn(obj);
        if(lv_btnm_get_btn_ctrl(obj, id, LV_BTNM_CTRL_INACTIVE)){
            return;
        }
        if(strcmp(txt, "Next word")==0){
            mnemonic[strlen(mnemonic)] = ' ';
        }else if(strcmp(txt, "<")==0){
            if(strlen(mnemonic) > 0){
                mnemonic[strlen(mnemonic)-1] = 0;
            }
        }else if(strcmp(txt, "Back")==0){
            memset(mnemonic, 0, sizeof(mnemonic));
            lv_async_call(gui_init_menu_show, lv_scr_act());
        }else if(strcmp(txt, "Done")==0){
            lv_async_call(gui_password_enter_show, lv_scr_act());
        }else{
            mnemonic[strlen(mnemonic)] = tolower(txt[0]);
        }
        gui_show_mnemonic(table, true);
    }
}

static lv_obj_t * gui_table_create(lv_obj_t * scr){
    static lv_style_t num_style;
    lv_style_copy(&num_style, &lv_style_transp);
    num_style.text.opa = LV_OPA_40;

    lv_obj_t * table = lv_table_create(scr, NULL);
    lv_table_set_col_cnt(table, 4);
    lv_table_set_row_cnt(table, 12);
    lv_table_set_col_width(table, 0, 50);
    lv_table_set_col_width(table, 2, 50);
    lv_table_set_col_width(table, 1, 150);
    lv_table_set_col_width(table, 3, 150);

    lv_table_set_style(table, LV_PAGE_STYLE_BG, &lv_style_transp);
    lv_table_set_style(table, LV_TABLE_STYLE_CELL1, &lv_style_transp);
    lv_table_set_style(table, LV_TABLE_STYLE_CELL2, &num_style);

    char msg[5] = "";
    for(int i=0; i<12; i++){
        sprintf(msg, "%d.", i+1);
        lv_table_set_cell_value(table, i, 0, msg);
        sprintf(msg, "%d.", i+13);
        lv_table_set_cell_value(table, i, 2, msg);
        lv_table_set_cell_type(table, i, 0, LV_TABLE_STYLE_CELL2);
        lv_table_set_cell_type(table, i, 2, LV_TABLE_STYLE_CELL2);
    }
    lv_obj_align(table, NULL, LV_ALIGN_IN_TOP_MID, 0, 100);
    return table;
}

void gui_mnemonic_enter_show(void * ptr){
    lv_obj_t * scr;
    if(ptr == NULL){
        scr = lv_scr_act();
    }else{
        scr = (lv_obj_t*)ptr;
    }
    lv_obj_clean(scr);

    memset(mnemonic, 0, sizeof(mnemonic));
    memset(password, 0, sizeof(password));

    gui_title_create(scr, "Enter your recovery phrase");

    table = gui_table_create(scr);

    // keyboard
    kb = lv_kb_create(scr, NULL);
    lv_obj_set_y(kb, LV_VER_RES*2/3);
    lv_obj_set_height(kb, LV_VER_RES/3);
    lv_kb_set_map(kb, keymap);

    lv_style_copy(&kb_dis_style, &lv_style_btn_ina);
    kb_dis_style.body.main_color = LV_COLOR_MAKE(0xe0,0xe0,0xe0);
    kb_dis_style.body.grad_color = LV_COLOR_MAKE(0xe0,0xe0,0xe0);
    kb_dis_style.body.radius = 0;
    kb_dis_style.body.border.opa = 30;
    lv_kb_set_style(kb, LV_KB_STYLE_BTN_INA, &kb_dis_style);

    lv_obj_set_event_cb(kb, cb_keyboard);
    lv_btnm_set_btn_ctrl(kb, 29, LV_BTNM_CTRL_INACTIVE);
    lv_btnm_set_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
    gui_show_mnemonic(table, true);
}

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

static void cb_init_keys(void * ptr){
    init_keys(mnemonic, password);
}

static void cb_pkeyboard(lv_obj_t * obj, lv_event_t event){
    if(event == LV_EVENT_CLICKED){
        const char * txt = lv_btnm_get_active_btn_text(obj);
        if(strcmp(txt, "<-")==0){
            if(strlen(password) > 0){
                password[strlen(password)-1] = 0;
            }
        }else if(strcmp(txt, "Clear")==0){
            memset(password, 0, sizeof(password));
        }else if(strcmp(txt, "Done")==0){
            lv_async_call(cb_init_keys, NULL);
        }else if(strcmp(txt,"^  ")==0){
            lv_kb_set_map(kb, pkeymapCap);
        }else if(strcmp(txt,"^ ")==0){
            lv_kb_set_map(kb, pkeymapLow);
        }else if(strcmp(txt,"#@")==0){
            lv_kb_set_map(kb, pkeymapNum);
        }else if(strcmp(txt,"aA")==0){
            lv_kb_set_map(kb, pkeymapLow);
        }else{
            password[strlen(password)] = txt[0];
        }
        lv_obj_t * ta = lv_kb_get_ta(obj);
        lv_ta_set_text(ta, password);
    }
}

void gui_password_enter_show(void * ptr){
    lv_obj_t * scr;
    if(ptr == NULL){
        scr = lv_scr_act();
    }else{
        scr = (lv_obj_t*)ptr;
    }
    lv_obj_clean(scr);

    memset(password, 0, sizeof(password));
    gui_title_create(scr, "Enter your password (optional)");

    // keyboard
    kb = lv_kb_create(scr, NULL);
    lv_obj_set_y(kb, LV_VER_RES*2/3);
    lv_obj_set_height(kb, LV_VER_RES*1/3);
    lv_kb_set_map(kb, pkeymapLow);
    lv_obj_set_event_cb(kb, cb_pkeyboard);

    /*Create a text area. The keyboard will write here*/
    lv_obj_t * ta = lv_ta_create(scr, NULL);
    lv_obj_set_size(ta, LV_HOR_RES-2*PADDING, 150);
    lv_ta_set_text(ta, password);
    // lv_ta_set_pwd_mode(ta, true); // password mode... tricky
    lv_obj_align(ta, NULL, LV_ALIGN_IN_TOP_MID, 0, 200);
    lv_obj_set_style(ta, &lv_style_transp);

    /*Assign the text area to the keyboard*/
    lv_kb_set_ta(kb, ta);
}
#endif