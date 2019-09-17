/**
 * @file tpcal.c
 *
 * TOUCHPAD CALIBRATION
 * ---------------------
 *
 * This application creates a GUI and instruct the user
 * to click the four corners to get data for touchpad calibration.
 *
 * - You display driver should have two functions: `xxx_read` and `xxx_set_cal_data`.
 * - At first run run the touchpad is not calibrated therefore your `xxx_read` function should provide raw data.
 * - When the user touched all four corners you should call the `xxx_set_cal_data` function in
 * ` TP_CAL_STATE_WAIT_LEAVE` state. As arguments you should pass `point[0]`, `point[1]`, `point[2]` and `point[3]`
 *   which are the coordinates read on corner pressing.
 * - `xxx_set_cal_data` should mark the display as calibrated, save the raw coordinates
 *    and use them in the upcoming calls of `xxx_read` to adjust the coordinates.
 * - A simple equation to adjust the coordinates: x_cal = ((x_act - x1_saved) * lcd_hor_res) / (x2_saved - x1_saved);
 *      - x_cal: the calibrated X coordinate
 *      - x_act: the currently measured X coordinate
 *      - x1_saved, x2_saved: The raw X coordinates saved as calibration data
 */

/*********************
 *      INCLUDES
 *********************/
#include "tpcal.h"
#include <stdio.h>
#include "touchpad.h"

/*********************
 *      DEFINES
 *********************/
#define CIRCLE_SIZE      20
#define CIRCLE_OFFSET    20
#define TP_MAX_VALUE     5000
#define TOUCH_NUMBER     3

/**********************
 *      TYPEDEFS
 **********************/
typedef enum {
    TP_CAL_STATE_INIT,
    TP_CAL_STATE_WAIT_TOP_LEFT,
    TP_CAL_STATE_WAIT_TOP_RIGHT,
    TP_CAL_STATE_WAIT_BOTTOM_RIGHT,
    TP_CAL_STATE_WAIT_BOTTOM_LEFT,
    TP_CAL_STATE_WAIT_LEAVE,
    TP_CAL_STATE_READY,
} tp_cal_state_t;

/**********************
 *  STATIC PROTOTYPES
 **********************/
static void get_avr_value(lv_point_t * p);
static void btn_event_cb(lv_obj_t * scr, lv_event_t event);

static void draw_rect();
static void update_rect();

/**********************
 *  STATIC VARIABLES
 **********************/
static lv_point_t point[4]; /*Calibration points: [0]: top-left; [1]: top-right, [2]: bottom-right, [3]: bottom-left */
static lv_point_t avr[TOUCH_NUMBER]; /*Storage point to calculate average*/

static tp_cal_state_t state;
static lv_obj_t * prev_scr;
static lv_obj_t * big_btn;
static lv_obj_t * label_main;
static lv_obj_t * circ_area;

static lv_obj_t * line;
static lv_point_t line_points[5];

static void (*callback)(lv_point_t * points);

/**********************
 *   GLOBAL FUNCTIONS
 **********************/

/**
 * Create a touch pad calibration screen
 */
void tpcal_create(void (*cb)(lv_point_t * points)){
    callback = cb;

    state = TP_CAL_STATE_INIT;

    prev_scr = lv_disp_get_scr_act(NULL);

    lv_obj_t * scr = lv_obj_create(NULL, NULL);
    lv_obj_set_size(scr, TP_MAX_VALUE, TP_MAX_VALUE);
    lv_disp_load_scr(scr);

    /*Create a big transparent button screen to receive clicks*/
    big_btn = lv_btn_create(lv_disp_get_scr_act(NULL), NULL);
    lv_obj_set_size(big_btn, TP_MAX_VALUE, TP_MAX_VALUE);
    lv_btn_set_style(big_btn, LV_BTN_STYLE_REL, &lv_style_transp);
    lv_btn_set_style(big_btn, LV_BTN_STYLE_PR, &lv_style_transp);
    lv_obj_set_event_cb(big_btn, btn_event_cb);
    lv_btn_set_layout(big_btn, LV_LAYOUT_OFF);

    lv_coord_t hres = lv_disp_get_hor_res(NULL);
    lv_coord_t vres = lv_disp_get_ver_res(NULL);

    lv_obj_t * title = lv_label_create(lv_disp_get_scr_act(NULL), NULL);
    lv_label_set_text(title, "First we need to calibrate the screen\n"
                            "If you failed and can't interact with GUI\n"
                            "just press the user button\n(blue on the back)"
    );
    lv_label_set_align(title, LV_LABEL_ALIGN_CENTER);
    lv_obj_set_pos(title, (hres - lv_obj_get_width(title)) / 2, 200);

    label_main = lv_label_create(lv_disp_get_scr_act(NULL), NULL);
    char buf[100];
    sprintf(buf, "Click the circle in the\n"
            "upper left-hand corner\n"
            "%u times left", TOUCH_NUMBER);
    lv_label_set_text(label_main, buf);
    lv_label_set_align(label_main, LV_LABEL_ALIGN_CENTER);

    lv_obj_set_pos(label_main, (hres - lv_obj_get_width(label_main)) / 2,
                   (vres - lv_obj_get_height(label_main)) / 2);


    static lv_style_t style_circ;
    lv_style_copy(&style_circ, &lv_style_pretty_color);
    style_circ.body.radius = LV_RADIUS_CIRCLE;

    circ_area = lv_obj_create(lv_disp_get_scr_act(NULL), NULL);
    lv_obj_set_size(circ_area, CIRCLE_SIZE, CIRCLE_SIZE);
    lv_obj_set_style(circ_area, &style_circ);
    lv_obj_set_click(circ_area, false);

#if LV_USE_ANIMATION
    lv_anim_t a;
    a.var = circ_area;
    a.start = hres / 2;
    a.end = CIRCLE_OFFSET;
    a.exec_cb = (lv_anim_exec_xcb_t)lv_obj_set_x;
    a.path_cb = lv_anim_path_linear;
    a.ready_cb = NULL;
    a.act_time = -500;
    a.time = 200;
    a.playback = 0;
    a.playback_pause = 0;
    a.repeat = 0;
    a.repeat_pause = 0;
    lv_anim_create(&a);

    a.start = vres / 2;
    a.end = CIRCLE_OFFSET;
    a.exec_cb = (lv_anim_exec_xcb_t)lv_obj_set_y;
    a.ready_cb = NULL;
    a.time = 200;
    lv_anim_create(&a);
#else
    lv_obj_set_pos(circ_area, CIRCLE_OFFSET, CIRCLE_OFFSET);
#endif

    draw_rect();

    state = TP_CAL_STATE_WAIT_TOP_LEFT;
}

/**********************
 *   STATIC FUNCTIONS
 **********************/

static void get_avr_value(lv_point_t * p)
{
    int32_t x_sum = 0;
    int32_t y_sum = 0;
    uint8_t i = 0;
    for(; i < TOUCH_NUMBER ; i++) {
        x_sum += avr[i].x;
        y_sum += avr[i].y;
    }
    p->x = x_sum / TOUCH_NUMBER;
    p->y = y_sum / TOUCH_NUMBER;
}

static void btn_event_cb(lv_obj_t * scr, lv_event_t event)
{
    (void) scr;    /*Unused*/

    if(event != LV_EVENT_CLICKED) return;

    lv_disp_t * disp = lv_obj_get_disp(prev_scr);
    lv_coord_t hres = lv_disp_get_hor_res(disp);
    lv_coord_t vres = lv_disp_get_ver_res(disp);

    static uint8_t touch_nb = TOUCH_NUMBER;

    if(state == TP_CAL_STATE_WAIT_TOP_LEFT) {
        char buf[64];
        touch_nb--;
        lv_indev_t * indev = lv_indev_get_act();
        lv_indev_get_point(indev, &avr[touch_nb]);

        if(!touch_nb) {
            touch_nb = TOUCH_NUMBER;
            get_avr_value(&point[0]);
            sprintf(buf, "x: %d\ny: %d", point[0].x, point[0].y);
            lv_obj_t * label_coord = lv_label_create(lv_disp_get_scr_act(disp), NULL);
            lv_label_set_text(label_coord, buf);
            sprintf(buf, "Click the circle in\n"
                    "upper right-hand corner\n"
                    " %u Left", TOUCH_NUMBER);
#if LV_USE_ANIMATION
            lv_anim_t a;
            a.var = circ_area;
            a.start = CIRCLE_OFFSET;
            a.end = hres - CIRCLE_SIZE - CIRCLE_OFFSET;
            a.exec_cb = (lv_anim_exec_xcb_t)lv_obj_set_x;
            a.path_cb = lv_anim_path_linear;
            a.ready_cb = NULL;
            a.act_time = 0;
            a.time = 200;
            a.playback = 0;
            a.playback_pause = 0;
            a.repeat = 0;
            a.repeat_pause = 0;
            lv_anim_create(&a);

            a.start = CIRCLE_OFFSET;
            a.end = CIRCLE_OFFSET;
            a.exec_cb = (lv_anim_exec_xcb_t)lv_obj_set_y;
            a.ready_cb = NULL;
            a.time = 200;
            lv_anim_create(&a);
#else
            lv_obj_set_pos(circ_area, LV_HOR_RES - CIRCLE_SIZE - CIRCLE_OFFSET, CIRCLE_OFFSET);
#endif
            state = TP_CAL_STATE_WAIT_TOP_RIGHT;
        } else {
            sprintf(buf, "Click the circle in\n"
                    "upper left-hand corner\n"
                    " %u Left", touch_nb);
        }
        lv_label_set_text(label_main, buf);
        lv_obj_set_pos(label_main, (hres - lv_obj_get_width(label_main)) / 2,
                       (vres - lv_obj_get_height(label_main)) / 2);


    } else if(state == TP_CAL_STATE_WAIT_TOP_RIGHT) {
        char buf[64];
        touch_nb--;
        lv_indev_t * indev = lv_indev_get_act();
        lv_indev_get_point(indev, &avr[touch_nb]);

        if(!touch_nb) {
            touch_nb = TOUCH_NUMBER;
            get_avr_value(&point[1]);
            sprintf(buf, "x: %d\ny: %d", point[1].x, point[1].y);
            lv_obj_t * label_coord = lv_label_create(lv_disp_get_scr_act(disp), NULL);
            lv_label_set_text(label_coord, buf);
            lv_obj_set_pos(label_coord, hres - lv_obj_get_width(label_coord), 0);
            sprintf(buf, "Click the circle in\n"
                    "lower right-hand corner\n"
                    " %u Left", TOUCH_NUMBER);
#if LV_USE_ANIMATION
            lv_anim_t a;
            a.var = circ_area;
            a.start = hres - CIRCLE_SIZE - CIRCLE_OFFSET;
            a.end = hres - CIRCLE_SIZE - CIRCLE_OFFSET;
            a.exec_cb = (lv_anim_exec_xcb_t)lv_obj_set_x;
            a.path_cb = lv_anim_path_linear;
            a.ready_cb = NULL;
            a.act_time = 0;
            a.time = 200;
            a.playback = 0;
            a.playback_pause = 0;
            a.repeat = 0;
            a.repeat_pause = 0;
            lv_anim_create(&a);

            a.start = CIRCLE_OFFSET;
            a.end = vres - CIRCLE_SIZE - CIRCLE_OFFSET;
            a.exec_cb = (lv_anim_exec_xcb_t)lv_obj_set_y;
            a.ready_cb = NULL;
            a.time = 200;
            lv_anim_create(&a);
#else
            lv_obj_set_pos(circ_area, hres - CIRCLE_SIZE - CIRCLE_OFFSET, vres - CIRCLE_SIZE - CIRCLE_OFFSET);
#endif
            state = TP_CAL_STATE_WAIT_BOTTOM_RIGHT;
        } else {
            sprintf(buf, "Click the circle in\n"
                    "upper right-hand corner\n"
                    " %u Left", touch_nb);
        }
        lv_label_set_text(label_main, buf);
        lv_obj_set_pos(label_main, (hres - lv_obj_get_width(label_main)) / 2,
                       (vres - lv_obj_get_height(label_main)) / 2);

    } else if(state == TP_CAL_STATE_WAIT_BOTTOM_RIGHT) {
        char buf[64];
        touch_nb--;
        lv_indev_t * indev = lv_indev_get_act();
        lv_indev_get_point(indev, &avr[touch_nb]);

        if(!touch_nb) {
            touch_nb = TOUCH_NUMBER;
            get_avr_value(&point[2]);
            sprintf(buf, "x: %d\ny: %d", point[2].x, point[2].y);
            lv_obj_t * label_coord = lv_label_create(scr, NULL);
            lv_label_set_text(label_coord, buf);
            sprintf(buf, "Click the circle in\n"
                    "lower left-hand corner\n"
                    " %u Left", TOUCH_NUMBER);
            lv_obj_set_pos(label_coord, hres - lv_obj_get_width(label_coord),
                           vres - lv_obj_get_height(label_coord));
#if LV_USE_ANIMATION
            lv_anim_t a;
            a.var = circ_area;
            a.start = hres - CIRCLE_SIZE - CIRCLE_OFFSET;
            a.end = CIRCLE_OFFSET;
            a.exec_cb = (lv_anim_exec_xcb_t)lv_obj_set_x;
            a.path_cb = lv_anim_path_linear;
            a.ready_cb = NULL;
            a.act_time = 0;
            a.time = 200;
            a.playback = 0;
            a.playback_pause = 0;
            a.repeat = 0;
            a.repeat_pause = 0;
            lv_anim_create(&a);

            a.start = vres - CIRCLE_SIZE - CIRCLE_OFFSET;
            a.end = vres - CIRCLE_SIZE - CIRCLE_OFFSET;
            a.exec_cb = (lv_anim_exec_xcb_t)lv_obj_set_y;
            a.ready_cb = NULL;
            a.time = 200;
            lv_anim_create(&a);
#else
            lv_obj_set_pos(circ_area, CIRCLE_OFFSET, LV_VER_RES - CIRCLE_SIZE - CIRCLE_OFFSET);
#endif
            state = TP_CAL_STATE_WAIT_BOTTOM_LEFT;
        } else {
            sprintf(buf, "Click the circle in\n"
                    "lower right-hand corner\n"
                    " %u Left", touch_nb);
        }
        lv_label_set_text(label_main, buf);
        lv_obj_set_pos(label_main, (hres - lv_obj_get_width(label_main)) / 2,
                       (vres - lv_obj_get_height(label_main)) / 2);
    } else if(state == TP_CAL_STATE_WAIT_BOTTOM_LEFT) {
        char buf[300];
        touch_nb--;
        lv_indev_t * indev = lv_indev_get_act();
        lv_indev_get_point(indev, &avr[touch_nb]);

        if(!touch_nb) {
            touch_nb = TOUCH_NUMBER;
            get_avr_value(&point[3]);
            sprintf(buf, "x: %d\ny: %d", point[3].x, point[3].y);
            lv_obj_t * label_coord = lv_label_create(scr, NULL);
            lv_label_set_text(label_coord, buf);
            lv_obj_set_pos(label_coord, 0, vres - lv_obj_get_height(label_coord));
            sprintf(buf, "Click the screen\n"
                    "to leave calibration");
            for(int i=0;i<4;i++){
                update_rect();
                sprintf(buf+strlen(buf),"\npoint%d: (%d,%d)", i, line_points[i].x, line_points[i].y);
            }
            lv_obj_del(circ_area);
            state = TP_CAL_STATE_WAIT_LEAVE;
        } else {
            sprintf(buf, "Click the circle in\n"
                    "lower left-hand corner\n"
                    " %u Left", touch_nb);
        }
        lv_label_set_text(label_main, buf);
        lv_obj_set_pos(label_main, (hres - lv_obj_get_width(label_main)) / 2,
                       (vres - lv_obj_get_height(label_main)) / 2);
    } else if(state == TP_CAL_STATE_WAIT_LEAVE) {
        lv_disp_load_scr(prev_scr);
        /*
         * TODO Process 'p' points here to calibrate the touch pad
         * Offset will be: CIRCLE_SIZE/2 + CIRCLE_OFFSET
         */
        callback(line_points);
        /*
         * TODO: you can change the calibrate input callback here e.g:
         *  lv_indev_t *indev = lv_indev_get_act();
         *  indev->driver.read = xxxx_input_get_calib;
         */

        state = TP_CAL_STATE_READY;

    } else if(state == TP_CAL_STATE_READY) {
    }
}

static void update_rect(){
    memcpy(line_points, point, sizeof(line_points));
    line_points[0].x -= CIRCLE_SIZE/2 + CIRCLE_OFFSET;
    line_points[0].y -= CIRCLE_SIZE/2 + CIRCLE_OFFSET;
    line_points[1].x += CIRCLE_SIZE/2 + CIRCLE_OFFSET;
    line_points[1].y -= CIRCLE_SIZE/2 + CIRCLE_OFFSET;
    line_points[2].x += CIRCLE_SIZE/2 + CIRCLE_OFFSET;
    line_points[2].y += CIRCLE_SIZE/2 + CIRCLE_OFFSET;
    line_points[3].x -= CIRCLE_SIZE/2 + CIRCLE_OFFSET;
    line_points[3].y += CIRCLE_SIZE/2 + CIRCLE_OFFSET;
    line_points[4] = line_points[0];
    lv_line_set_points(line, line_points, 5);     /*Set the points*/
}

static void draw_rect(){
    static lv_style_t style_line;
    lv_style_copy(&style_line, &lv_style_plain);
    style_line.line.color = LV_COLOR_MAKE(0xaa, 0xaa, 0xaa);
    style_line.line.width = 1;
    style_line.line.rounded = 1;

    // get rid of previous calibration
    line_points[0].x = 0;
    line_points[0].y = 0;
    line_points[1].x = LV_HOR_RES;
    line_points[1].y = 0;
    line_points[2].x = LV_HOR_RES;
    line_points[2].y = LV_VER_RES;
    line_points[3].x = 0;
    line_points[3].y = LV_VER_RES;

    tounchpad_calibrate(line_points);

    /*Copy the previous line and apply the new style*/
    line = lv_line_create(lv_scr_act(), NULL);
    lv_line_set_style(line, LV_LINE_STYLE_MAIN, &style_line);
    // lv_obj_align(line, NULL, LV_ALIGN_CENTER, 0, 0);
    // update_rect();
}
