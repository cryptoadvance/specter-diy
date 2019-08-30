#ifndef GUI_H
#define GUI_H

#include "lvgl.h"
#include "main.h"
#include "./alert/alert.h"
#include "./mnemonic/mnemonic.h"

void gui_init();
void gui_start();
void gui_update();
void gui_calibrate(); // trigger calibration again
void gui_init_menu_show(void * ptr);
void gui_main_menu_show(void * ptr);
void fs_err(const char * msg);
// // full screens
// lv_obj_t * gui_alert(const char * title, const char * message, void (*callback)(lv_obj_t * btn, lv_event_t event));

// // elements
// lv_obj_t * gui_create_title(const char * title);
// lv_obj_t * gui_create_button(const char * text, void (*callback)(lv_obj_t * btn, lv_event_t event));

#endif