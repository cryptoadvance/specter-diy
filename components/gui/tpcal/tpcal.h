/**
 * @file tpcal.h
 *
 */

#ifndef TPCAL_H
#define TPCAL_H

#ifdef __cplusplus
extern "C" {
#endif

#include "lvgl.h"

/**
 * Create a touch pad calibration screen
 */
void tpcal_create(void (*cb)(lv_point_t * points));

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /*TP_CAL_H*/
