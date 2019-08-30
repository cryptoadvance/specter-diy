/**
 * @file indev.c
 *
 */

/*********************
 *      INCLUDES
 *********************/
#include "stm32f4xx.h"

#include "stm32469i_discovery.h"
#include "stm32469i_discovery_ts.h"
#include "lvgl.h"
#include "tft.h"

/*********************
 *      DEFINES
 *********************/

/**********************
 *      TYPEDEFS
 **********************/

/**********************
 *  STATIC PROTOTYPES
 **********************/
static bool touchpad_read(lv_indev_drv_t * drv, lv_indev_data_t *data);
static void touchpad_correct(lv_point_t * point);

/**********************
 *  STATIC VARIABLES
 **********************/
static TS_StateTypeDef  TS_State;
static lv_point_t pcal[4]; // calibration points

/**********************
 *      MACROS
 **********************/

/**********************
 *   GLOBAL FUNCTIONS
 **********************/

/**
 * Initialize your input devices here
 */
void touchpad_init(void)
{
  BSP_TS_Init(TFT_HOR_RES, TFT_VER_RES);

  lv_indev_drv_t indev_drv;
  lv_indev_drv_init(&indev_drv);
  indev_drv.read_cb = touchpad_read;
  indev_drv.type = LV_INDEV_TYPE_POINTER;
  lv_indev_drv_register(&indev_drv);

  pcal[0].x = 0;
  pcal[0].y = 0;
  pcal[1].x = TFT_HOR_RES;
  pcal[1].y = 0;
  pcal[2].x = TFT_HOR_RES;
  pcal[2].y = TFT_VER_RES;
  pcal[3].x = 0;
  pcal[3].y = TFT_VER_RES;
}

void tounchpad_calibrate(const lv_point_t * points){
	memcpy(pcal, points, sizeof(pcal));
}

/**********************
 *   STATIC FUNCTIONS
 **********************/

static void touchpad_correct(lv_point_t * point){
	int16_t x = point->x;
	int16_t y = point->y;
	int16_t x1 = (pcal[0].x*(TFT_VER_RES-y)+pcal[3].x*y)/TFT_VER_RES;
	int16_t x2 = (pcal[1].x*(TFT_VER_RES-y)+pcal[2].x*y)/TFT_VER_RES;
	int16_t y1 = (pcal[0].y*(TFT_HOR_RES-x)+pcal[1].y*x)/TFT_HOR_RES;
	int16_t y2 = (pcal[3].y*(TFT_HOR_RES-x)+pcal[2].y*x)/TFT_HOR_RES;
	point->x = TFT_HOR_RES * (x-x1)/(x2-x1);
	point->y = TFT_VER_RES * (y-y1)/(y2-y1);
}
/**
 * Read an input device
 * @param indev_id id of the input device to read
 * @param x put the x coordinate here
 * @param y put the y coordinate here
 * @return true: the device is pressed, false: released
 */
static bool touchpad_read(lv_indev_drv_t * drv, lv_indev_data_t *data)
{
	static int16_t last_x = 0;
	static int16_t last_y = 0;

	BSP_TS_GetState(&TS_State);
	if(TS_State.touchDetected != 0) {
		lv_point_t point;
		point.x = TS_State.touchX[0];
		point.y = TS_State.touchY[0];
		touchpad_correct(&point);
		data->point = point;
		last_x = data->point.x;
		last_y = data->point.y;
		data->state = LV_INDEV_STATE_PR;
	} else {
		data->point.x = last_x;
		data->point.y = last_y;
		data->state = LV_INDEV_STATE_REL;
	}

	return false;
}
