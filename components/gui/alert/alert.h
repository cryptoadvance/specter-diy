/**
 * @file tpcal.h
 *
 */

#ifndef GUI_ALERT_H
#define GUI_ALERT_H

#include "lvgl.h"

/**
 * Create an alert. 
 * Button returns back to the screen active 
 * at the moment of the function call.
 * If btntext is NULL there will be no button.
 * (for example for critical errors)
 *
 * Returns the pointer to the message label
 * (if you want to change it)
 */
lv_obj_t * gui_alert_create(const char * title, 
					  const char * message, 
					  const char * btntext);

lv_obj_t * gui_qr_alert_create(const char * title, 
					  const char * qr_text,
					  const char * message, 
					  const char * btntext);

#endif /* GUI_ALERT_H */
