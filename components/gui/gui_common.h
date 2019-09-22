#ifndef GUI_COMMON_H
#define GUI_COMMON_H

#include "lvgl.h"

#define PADDING 30
#define BTN_HEIGHT 80

// Title style. Should be defined somewhere.
extern lv_style_t title_style;

lv_obj_t * gui_title_create(lv_obj_t * scr, 
							 const char * title,
							 bool no_style = false // to appear as a normal label
			);

lv_obj_t * gui_button_create(lv_obj_t * scr, 
							 const char * text, 
							 void (*callback)(lv_obj_t * btn, lv_event_t event)
			);
lv_obj_t * gui_qr_create(lv_obj_t * scr, uint16_t width, const char * text);

#endif /* GUI_COMMON_H */
