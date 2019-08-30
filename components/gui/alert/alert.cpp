#include "alert.h"
#include "../gui_common.h"
#include <stdio.h>

static lv_obj_t * prev_scr;

static void cb_back(lv_obj_t * btn, lv_event_t event){
    if(event == LV_EVENT_CLICKED){
        lv_disp_load_scr(prev_scr);
    }
}

lv_obj_t * gui_alert_create(const char * title, 
                      const char * message, 
                      const char * btntext){
    prev_scr = lv_disp_get_scr_act(NULL);

    lv_obj_t * scr = lv_obj_create(NULL, NULL);

    lv_obj_t * obj = gui_title_create(scr, title);

    // create main text
    lv_obj_t * txt = lv_label_create(scr, NULL);
    lv_label_set_text(txt, message);
    lv_label_set_long_mode(txt, LV_LABEL_LONG_BREAK);
    lv_obj_set_width(txt, LV_HOR_RES-2*PADDING);
    lv_obj_align(txt, NULL, LV_ALIGN_IN_TOP_MID, 0, 0);
    lv_label_set_align(obj, LV_LABEL_ALIGN_CENTER);
    lv_obj_set_y(txt, lv_obj_get_y(obj) + lv_obj_get_height(obj) + PADDING);

    if(btntext != NULL){
        // create button
        gui_button_create(scr, btntext, cb_back);
    }
    lv_disp_load_scr(scr);
    return txt;
}