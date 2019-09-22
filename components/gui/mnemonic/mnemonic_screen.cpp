#include "mnemonic.h"
#include <stdio.h>
#include "lvgl.h"
#include "wally_bip39.h"
extern "C" {
    #include "utility/wordlist.h"
}

#include "../gui_common.h"
#include "../gui.h"

lv_obj_t * gui_mnemonic_table_create(lv_obj_t * scr, const char * mnemonic){
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

    gui_show_mnemonic(table, mnemonic, NULL);

    return table;
}

void gui_show_mnemonic(lv_obj_t * tbl, const char * mnemonic, bool highlight){
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
    if(highlight){
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
    int wordcount = cellnum+1;
    if(wordcount < 24){
        lv_table_set_cell_value(tbl, wordcount % 12, 1+2*(wordcount/12), "");
    }
}

static struct words * wordlist = NULL;

void gui_check_mnemonic(const char * mnemonic, lv_obj_t * kb){
    if(wordlist == NULL){
        bip39_get_wordlist(NULL, &wordlist);
    }
    const char * lastWord = mnemonic;
    for(int i=strlen(mnemonic)-1; i>=0; i--){
        if(mnemonic[i]==' '){
            lastWord = mnemonic+i+1;
            break;
        }
    }
    if(strlen(lastWord) > 0){
        bool correct = (wordlist_lookup_word(wordlist, lastWord) > 0);
        if(correct){
            lv_btnm_clear_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
        }else{
            lv_btnm_set_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
        }
    }else{
        lv_btnm_set_btn_ctrl(kb, 29, LV_BTNM_CTRL_INACTIVE);
        lv_btnm_set_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
    }

    int wordcount = 1;
    for(int i=0; i<strlen(mnemonic); i++){
        if(mnemonic[i] == ' '){
            wordcount++;
        }
    }
    if(wordcount == 24){
        lv_btnm_set_btn_ctrl(kb, 28, LV_BTNM_CTRL_INACTIVE);
    }
    if(wordcount>=12 && (wordcount % 3 == 0)){
        if(bip39_mnemonic_validate(NULL, mnemonic) == 0){
            lv_btnm_clear_btn_ctrl(kb, 29, LV_BTNM_CTRL_INACTIVE);
        }else{
            lv_btnm_set_btn_ctrl(kb, 29, LV_BTNM_CTRL_INACTIVE);
        }
    }
}