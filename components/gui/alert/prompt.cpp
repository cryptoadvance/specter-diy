#include "alert.h"
#include "../gui_common.h"
#include <stdio.h>

static lv_obj_t * prev_scr;
static void (*ok_cb)(void * ptr);
static void (*cancel_cb)(void * ptr);

static void cb_ok(lv_obj_t * btn, lv_event_t event){
    if(event == LV_EVENT_CLICKED){
        lv_disp_load_scr(prev_scr);
        if(ok_cb != NULL){
            lv_async_call(ok_cb, NULL);
        }
    }
}

static void cb_cancel(lv_obj_t * btn, lv_event_t event){
    if(event == LV_EVENT_CLICKED){
        lv_disp_load_scr(prev_scr);
        if(cancel_cb != NULL){
            lv_async_call(cancel_cb, NULL);
        }
    }
}

lv_obj_t * gui_prompt_create(const char * title, 
                      const char * message, 
                      const char * ok_text, 
                      void (*ok_callback)(void * ptr), 
                      const char * cancel_text, 
                      void (*cancel_callback)(void * ptr)){
    prev_scr = lv_disp_get_scr_act(NULL);

    lv_obj_t * scr = lv_obj_create(NULL, NULL);

    lv_obj_t * obj = gui_title_create(scr, title);

    ok_cb = ok_callback;
    cancel_cb = cancel_callback;

    // create main text
    lv_obj_t * txt = lv_label_create(scr, NULL);
    lv_label_set_text(txt, message);
    lv_label_set_long_mode(txt, LV_LABEL_LONG_BREAK);
    lv_obj_set_width(txt, LV_HOR_RES-2*PADDING);
    lv_obj_align(txt, NULL, LV_ALIGN_IN_TOP_MID, 0, 0);
    lv_label_set_align(obj, LV_LABEL_ALIGN_CENTER);
    lv_obj_set_y(txt, lv_obj_get_y(obj) + lv_obj_get_height(obj) + PADDING);

    // create button
    lv_obj_t * btn;
    btn = gui_button_create(scr, cancel_text, cb_cancel);
    lv_obj_set_width(btn, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(btn, PADDING);
    btn = gui_button_create(scr, ok_text, cb_ok);
    lv_obj_set_width(btn, LV_HOR_RES/2-3*PADDING/2);
    lv_obj_set_x(btn, LV_HOR_RES/2+PADDING/2);

    lv_disp_load_scr(scr);
    return txt;
}