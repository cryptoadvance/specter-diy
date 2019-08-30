#include "gui_common.h"
#include "qrcode.h"
#include <stdlib.h>

lv_obj_t * gui_title_create(lv_obj_t * scr, const char * title){
    if(scr == NULL){
        scr = lv_scr_act();
    }
    lv_obj_t * obj = lv_label_create(scr, NULL);
    lv_obj_set_style(obj, &title_style);
    lv_label_set_text(obj, title);
    lv_label_set_long_mode(obj, LV_LABEL_LONG_BREAK);
    lv_obj_set_width(obj, LV_HOR_RES);
    lv_label_set_align(obj, LV_LABEL_ALIGN_CENTER);
    lv_obj_set_y(obj, PADDING);
    return obj;
}

lv_obj_t * gui_button_create(lv_obj_t * scr, const char * text, void (*callback)(lv_obj_t * btn, lv_event_t event)){
    if(scr == NULL){
        scr = lv_scr_act();
    }
    // button
    lv_obj_t * obj = lv_btn_create(scr, NULL);
    lv_obj_set_event_cb(obj, callback);
    lv_obj_set_width(obj, LV_HOR_RES-2*PADDING);
    lv_obj_set_height(obj, BTN_HEIGHT);
    // button label
    lv_obj_t * lbl = lv_label_create(obj, NULL);
    lv_label_set_text(lbl, text);
    lv_label_set_align(lbl, LV_LABEL_ALIGN_CENTER);
    // alignment
    lv_obj_align(obj, NULL, LV_ALIGN_IN_TOP_MID, 0, 0);
    lv_obj_set_y(obj, 700);
    return obj;
}

lv_obj_t * gui_qr_create(lv_obj_t * scr, uint16_t width, const char * text){
    static lv_color_t * cbuf;
    if(cbuf != NULL){
        free(cbuf);
        cbuf = NULL;
    }
    if(scr == NULL){
        scr = lv_scr_act();
    }
    lv_obj_t * obj = lv_canvas_create(scr, NULL);
    cbuf = (lv_color_t*)calloc(LV_CANVAS_BUF_SIZE_INDEXED_1BIT(width, width), sizeof(lv_color_t));
    lv_obj_set_size(obj, width, width);

    lv_canvas_set_buffer(obj, cbuf, width, width, LV_IMG_CF_INDEXED_1BIT);
    lv_canvas_set_palette(obj, 0, LV_COLOR_TRANSP);
    lv_canvas_set_palette(obj, 1, LV_COLOR_BLACK);

    lv_color_t c0;
    lv_color_t c1;
    c0.full = 0;
    c1.full = 1;

    /*Transparent background*/
    lv_canvas_fill_bg(obj, c0);

    int qrSize = 10;
    int sizes[] = { 14, 26, 42, 62, 84, 106, 122, 152, 180, 213, 251, 287, 331, 362, 412, 480, 504, 560, 624, 666, 711, 779, 857, 911, 997, 1059, 1125, 1190 };
    int len = strlen(text);
    for(int i=0; i<sizeof(sizes)/sizeof(int); i++){
        if(sizes[i] > len){
            qrSize = i+1;
            break;
        }
    }

    QRCode qrcode;
    uint8_t * qrcodeData = (uint8_t *)calloc(qrcode_getBufferSize(qrSize), sizeof(uint8_t));
    qrcode_initText(&qrcode, qrcodeData, qrSize, 1, text);

    if(qrcode.size <= width){
        uint16_t scale = width/qrcode.size;
        uint16_t padding = (width % qrcode.size)/2;
        for (uint16_t y = 0; y < qrcode.size; y++) {
            for (uint16_t x = 0; x < qrcode.size; x++) {
                if(qrcode_getModule(&qrcode, x, y)){
                    for(uint16_t xx = 0; xx<scale; xx++){
                        for(uint16_t yy = 0; yy<scale; yy++){
                            lv_canvas_set_px(obj, xx+x*scale+padding, yy+y*scale+padding, c1);
                        }
                    }
                }
            }
        }
    }
    free(qrcodeData);

    lv_obj_align(obj, NULL, LV_ALIGN_IN_TOP_MID, 0, lv_obj_get_y(obj));
    return obj;
}