/**
 * @file indev.h
 *
 */

#ifndef INDEV_H
#define INDEV_H

/*********************
 *      INCLUDES
 *********************/
#include <stdbool.h>
#include <stdint.h>
#include <lvgl.h>

/*********************
 *      DEFINES
 *********************/

/**********************
 *      TYPEDEFS
 **********************/

 #ifdef __cplusplus
 extern "C" {
 #endif

/**********************
 * GLOBAL PROTOTYPES
 **********************/
void touchpad_init(void);
void tounchpad_calibrate(const lv_point_t * points);

/**********************
 *      MACROS
 **********************/

 #ifdef __cplusplus
 } /* extern "C" */
 #endif

#endif
