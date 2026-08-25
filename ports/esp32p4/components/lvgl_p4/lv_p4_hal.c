/**
 * @file lv_p4_hal.c
 * @brief LVGL bound to the p4board panel and GT911 touch.
 *
 * Modelado a partir de f469-disco/usermods/udisplay_f469/lv_stm_hal/, que faz
 * o mesmo para a Discovery F469 em 73 linhas.
 *
 * Diferenca principal: o F469 renderiza num buffer de trabalho e copia para o
 * LTDC a cada flush. Aqui o LVGL desenha DIRETO no framebuffer que o
 * controlador DPI varre -- p4board_framebuffer() devolve exatamente essa
 * memoria, e lv_conf.h esta em RGB565 para casar com o formato do painel.
 * O flush entao so precisa avisar o painel de qual faixa mudou.
 */

#include "lv_p4_hal.h"

#include "board_config.h"
#include "esp_log.h"
#include "lv_conf.h"
#include "lvgl.h"
#include "p4board.h"

static const char *TAG = "lv-p4";

static void tft_flush(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map);
static void touchpad_read(lv_indev_t *indev, lv_indev_data_t *data);

void tft_init(void) {
    if (p4board_display_init() != ESP_OK) {
        ESP_LOGE(TAG, "panel init failed; LVGL will have nothing to draw on");
        return;
    }

    uint16_t *framebuffer = p4board_framebuffer();
    size_t nbytes = (size_t)P4BOARD_LCD_WIDTH * P4BOARD_LCD_HEIGHT * 2u;

    lv_display_t *disp = lv_display_create(P4BOARD_LCD_WIDTH, P4BOARD_LCD_HEIGHT);
    lv_display_set_flush_cb(disp, tft_flush);
    /* DIRECT: o buffer do LVGL e o framebuffer do painel, sem copia. */
    lv_display_set_buffers(disp, framebuffer, NULL, nbytes,
        LV_DISPLAY_RENDER_MODE_DIRECT);

    p4board_backlight(100);
    ESP_LOGI(TAG, "LVGL on %ux%u RGB565, direct render",
        P4BOARD_LCD_WIDTH, P4BOARD_LCD_HEIGHT);
}

static void tft_flush(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map) {
    (void)px_map;  /* Ja e o framebuffer: nao ha o que copiar. */

    if (area->y2 >= area->y1) {
        int32_t y = area->y1 < 0 ? 0 : area->y1;
        int32_t height = area->y2 - y + 1;
        if (y < P4BOARD_LCD_HEIGHT) {
            if (height > P4BOARD_LCD_HEIGHT - y) {
                height = P4BOARD_LCD_HEIGHT - y;
            }
            /* O painel DPI varre continuamente e as escritas RGB565 ficam em
             * cache. Commitar a faixa inteira evita as bandas e linhas
             * fantasma que aparecem ao commitar so as scanlines do texto. */
            p4board_flush((uint16_t)y, (uint16_t)height);
        }
    }
    lv_display_flush_ready(disp);
}

void touchpad_init(void) {
    if (p4board_touch_init() != ESP_OK) {
        ESP_LOGE(TAG, "touch init failed; the UI will be display-only");
        return;
    }
    lv_indev_t *indev = lv_indev_create();
    lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(indev, touchpad_read);
    ESP_LOGI(TAG, "GT911 registered at 0x%02x", p4board_touch_address());
}

static void touchpad_read(lv_indev_t *indev, lv_indev_data_t *data) {
    (void)indev;
    /* O LVGL espera a ultima posicao conhecida junto com o estado RELEASED,
     * senao um toque que termina fora do widget cancela o clique. */
    static int32_t last_x = 0;
    static int32_t last_y = 0;

    p4board_touch_point_t points[P4BOARD_TOUCH_MAX_POINTS];
    uint8_t count = 0;

    if (p4board_touch_read(points, P4BOARD_TOUCH_MAX_POINTS, &count) == ESP_OK
        && count > 0) {
        last_x = points[0].x;
        last_y = points[0].y;
        data->state = LV_INDEV_STATE_PRESSED;
    } else {
        data->state = LV_INDEV_STATE_RELEASED;
    }
    data->point.x = last_x;
    data->point.y = last_y;
}
