#ifndef GUI_MNEMONIC_H
#define GUI_MNEMONIC_H

#include "lvgl.h"

lv_obj_t * gui_mnemonic_table_create(lv_obj_t * scr, const char * mnemonic);
void gui_show_mnemonic(lv_obj_t * tbl, const char * mnemonic, bool highlight = false);
void gui_check_mnemonic(const char * mnemonic, lv_obj_t * kb);

#endif /* GUI_MNEMONIC_H */
