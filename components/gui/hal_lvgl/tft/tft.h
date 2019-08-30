/**
 * @file disp.h
 *
 */

#ifndef DISP_H
#define DISP_H

/*********************
 *      INCLUDES
 *********************/
#include <stdint.h>
#include "lvgl.h"

/*********************
 *      DEFINES
 *********************/
#define TFT_HOR_RES LV_HOR_RES
#define TFT_VER_RES LV_VER_RES

#define TFT_EXT_FB		1		/*Frame buffer is located into an external SDRAM*/
#define TFT_USE_GPU		1		/*Enable hardware accelerator*/

/**********************
 *      TYPEDEFS
 **********************/

 #ifdef __cplusplus
 extern "C" {
 #endif

/**********************
 * GLOBAL PROTOTYPES
 **********************/
void tft_init(void);

/**********************
 *      MACROS
 **********************/
 #ifdef __cplusplus
 } /* extern "C" */
 #endif

#endif
