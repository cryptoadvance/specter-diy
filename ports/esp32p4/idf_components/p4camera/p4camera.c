/**
 * @file p4camera.c
 * @brief Captura MIPI-CSI em tons de cinza para leitura de QR.
 *
 * Modelado a partir de odudex/Kern, components/video/video.c (MIT), reduzido ao
 * que a leitura de QR precisa: um sensor, um formato, sem foco automatico, sem
 * pipeline de exibicao.
 *
 * Duas escolhas herdadas do Kern e que importam nesta placa:
 *
 *   - O SCCB da camera divide o barramento I2C com o touch (GPIO 8/7), entao
 *     init_sccb fica false e o handle vem do p4board. Abrir um segundo master
 *     bus nos mesmos pinos falha.
 *   - O sensor e sondado por endereco em vez de assumido: a Waveshare 4.3
 *     costuma vir com OV5647, mas placas irmas trazem SC2336.
 *
 * Formato: V4L2_PIX_FMT_GREY. O quirc trabalha em tons de cinza, entao pedir
 * GREY ao sensor evita converter a cada quadro.
 */

#include "p4camera.h"

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "driver/i2c_master.h"
#include "esp_log.h"
#include "esp_video_device.h"
#include "esp_video_init.h"
#include "k_quirc.h"
#include "linux/videodev2.h"

#define OV5647_SCCB_ADDR 0x36
#define SC2336_SCCB_ADDR 0x30
#define BUFFER_COUNT     2

static const char *TAG = "p4camera";

static int video_fd = -1;
static p4camera_sensor_t sensor = P4CAM_SENSOR_NONE;
static uint16_t frame_width;
static uint16_t frame_height;
static uint8_t *buffers[BUFFER_COUNT];
static size_t buffer_lengths[BUFFER_COUNT];
static struct v4l2_buffer current;
static uint32_t pixel_format;
/* Em que etapa a inicializacao parou. Os ESP_LOG nao chegam ao REPL cru do
 * MicroPython, entao a etapa precisa ser consultavel do lado Python. */
static const char *init_stage = "not started";

/* Buffer em tons de cinza para o decodificador de QR. Declarado aqui, junto
 * do restante do estado, porque p4camera_deinit() o libera e vem antes das
 * funcoes de QR no arquivo. */
static uint8_t *gray_buffer;
static uint16_t gray_width;
static uint16_t gray_height;
static bool holding_frame;
static bool streaming;

/* Declarado em p4board.h; evitamos incluir o header do board aqui para manter
 * este componente independente da BSP. */
extern void *p4board_i2c_bus(void);

static bool probe_sensor(i2c_master_bus_handle_t bus) {
    if (i2c_master_probe(bus, OV5647_SCCB_ADDR, 100) == ESP_OK) {
        sensor = P4CAM_SENSOR_OV5647;
        return true;
    }
    if (i2c_master_probe(bus, SC2336_SCCB_ADDR, 100) == ESP_OK) {
        sensor = P4CAM_SENSOR_SC2336;
        return true;
    }
    sensor = P4CAM_SENSOR_NONE;
    return false;
}

static esp_err_t start_streaming(void) {
    struct v4l2_requestbuffers req = {
        .count = BUFFER_COUNT,
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .memory = V4L2_MEMORY_MMAP,
    };
    if (ioctl(video_fd, VIDIOC_REQBUFS, &req) != 0) {
        ESP_LOGE(TAG, "REQBUFS failed: %s", strerror(errno));
        return ESP_FAIL;
    }

    for (int i = 0; i < BUFFER_COUNT; ++i) {
        struct v4l2_buffer buf = {
            .index = i,
            .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
            .memory = V4L2_MEMORY_MMAP,
        };
        if (ioctl(video_fd, VIDIOC_QUERYBUF, &buf) != 0) {
            ESP_LOGE(TAG, "QUERYBUF %d failed: %s", i, strerror(errno));
            return ESP_FAIL;
        }
        buffers[i] = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED,
            video_fd, buf.m.offset);
        if (buffers[i] == MAP_FAILED) {
            buffers[i] = NULL;
            ESP_LOGE(TAG, "mmap %d failed: %s", i, strerror(errno));
            return ESP_FAIL;
        }
        buffer_lengths[i] = buf.length;
        if (ioctl(video_fd, VIDIOC_QBUF, &buf) != 0) {
            ESP_LOGE(TAG, "QBUF %d failed: %s", i, strerror(errno));
            return ESP_FAIL;
        }
    }

    int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(video_fd, VIDIOC_STREAMON, &type) != 0) {
        ESP_LOGE(TAG, "STREAMON failed: %s", strerror(errno));
        return ESP_FAIL;
    }
    streaming = true;
    return ESP_OK;
}

esp_err_t p4camera_init(void) {
    if (video_fd >= 0) {
        return ESP_OK;
    }

    i2c_master_bus_handle_t bus = (i2c_master_bus_handle_t)p4board_i2c_bus();
    if (bus == NULL) {
        ESP_LOGE(TAG, "I2C bus not up; call p4board touch init first");
        return ESP_ERR_INVALID_STATE;
    }
    if (!probe_sensor(bus)) {
        ESP_LOGE(TAG, "no camera sensor at 0x%02x or 0x%02x -- module attached?",
            OV5647_SCCB_ADDR, SC2336_SCCB_ADDR);
        return ESP_ERR_NOT_FOUND;
    }
    ESP_LOGI(TAG, "sensor: %s", p4camera_sensor_name());

    esp_video_init_csi_config_t csi_config = {
        .sccb_config = {
            .init_sccb = false,   /* barramento compartilhado com o touch */
            .i2c_handle = bus,
            .freq = 100000,
        },
        .reset_pin = -1,
        .pwdn_pin = -1,
    };
    esp_video_init_config_t config = { .csi = &csi_config };
    esp_err_t err = esp_video_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_video_init failed: %s", esp_err_to_name(err));
        init_stage = "esp_video_init";
        return err;
    }

    video_fd = open(ESP_VIDEO_MIPI_CSI_DEVICE_NAME, O_RDWR);
    if (video_fd < 0) {
        ESP_LOGE(TAG, "open %s failed: %s", ESP_VIDEO_MIPI_CSI_DEVICE_NAME,
            strerror(errno));
        init_stage = "open";
        return ESP_FAIL;
    }

    struct v4l2_format format = { .type = V4L2_BUF_TYPE_VIDEO_CAPTURE };
    if (ioctl(video_fd, VIDIOC_G_FMT, &format) != 0) {
        ESP_LOGE(TAG, "G_FMT failed: %s", strerror(errno));
        init_stage = "G_FMT";
        goto fail;
    }
    frame_width = format.fmt.pix.width;
    frame_height = format.fmt.pix.height;

    /* Escolher o formato em vez de exigir um.
     *
     * O quirc trabalha em luminancia, entao GREY seria ideal -- um plano, sem
     * conversao. Mas nem todo sensor entrega GREY pelo pipeline CSI, e um
     * S_FMT recusado derruba a inicializacao inteira. Enumeramos o que o
     * driver oferece e ficamos com o melhor disponivel, guardando a escolha
     * para quem for decodificar saber o que recebeu. */
    static const uint32_t preferred[] = {
        V4L2_PIX_FMT_GREY,     /* melhor: ja e luminancia */
        V4L2_PIX_FMT_RGB565,   /* aceitavel: converter por quadro */
        V4L2_PIX_FMT_SBGGR8,   /* Bayer cru: o canal verde serve de aproximacao */
    };
    uint32_t chosen = format.fmt.pix.pixelformat;
    bool picked = false;
    for (size_t rank = 0; rank < sizeof(preferred) / sizeof(preferred[0])
        && !picked; ++rank) {
        struct v4l2_fmtdesc desc = { .type = V4L2_BUF_TYPE_VIDEO_CAPTURE };
        for (desc.index = 0; ioctl(video_fd, VIDIOC_ENUM_FMT, &desc) == 0;
            ++desc.index) {
            if (desc.pixelformat == preferred[rank]) {
                chosen = preferred[rank];
                picked = true;
                break;
            }
        }
    }
    if (chosen != format.fmt.pix.pixelformat) {
        struct v4l2_format want = {
            .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
            .fmt.pix.width = frame_width,
            .fmt.pix.height = frame_height,
            .fmt.pix.pixelformat = chosen,
        };
        if (ioctl(video_fd, VIDIOC_S_FMT, &want) != 0) {
            ESP_LOGE(TAG, "S_FMT %c%c%c%c failed: %s",
                (char)(chosen), (char)(chosen >> 8), (char)(chosen >> 16),
                (char)(chosen >> 24), strerror(errno));
            init_stage = "S_FMT";
            goto fail;
        }
    }
    pixel_format = chosen;

    if (start_streaming() != ESP_OK) {
        init_stage = "streaming";
        goto fail;
    }
    init_stage = "ok";
    ESP_LOGI(TAG, "streaming %ux%u fmt=%c%c%c%c", frame_width, frame_height,
        (char)(pixel_format), (char)(pixel_format >> 8),
        (char)(pixel_format >> 16), (char)(pixel_format >> 24));
    return ESP_OK;

fail:
    p4camera_deinit();
    return ESP_FAIL;
}

void p4camera_deinit(void) {
    if (video_fd >= 0) {
        if (streaming) {
            int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
            ioctl(video_fd, VIDIOC_STREAMOFF, &type);
            streaming = false;
        }
        for (int i = 0; i < BUFFER_COUNT; ++i) {
            if (buffers[i]) {
                munmap(buffers[i], buffer_lengths[i]);
                buffers[i] = NULL;
                buffer_lengths[i] = 0;
            }
        }
        close(video_fd);
        video_fd = -1;
    }
    holding_frame = false;
    frame_width = frame_height = 0;
    sensor = P4CAM_SENSOR_NONE;
    free(gray_buffer);
    gray_buffer = NULL;
    gray_width = gray_height = 0;
}

const char *p4camera_init_stage(void) {
    return init_stage;
}

uint32_t p4camera_format(void) {
    return pixel_format;
}

p4camera_sensor_t p4camera_sensor(void) {
    return sensor;
}

const char *p4camera_sensor_name(void) {
    switch (sensor) {
        case P4CAM_SENSOR_OV5647: return "OV5647";
        case P4CAM_SENSOR_SC2336: return "SC2336";
        default: return "none";
    }
}

void p4camera_size(uint16_t *width, uint16_t *height) {
    if (width) *width = frame_width;
    if (height) *height = frame_height;
}

esp_err_t p4camera_capture(uint8_t **data, size_t *length) {
    if (video_fd < 0 || !streaming) {
        return ESP_ERR_INVALID_STATE;
    }
    if (holding_frame) {
        /* Segurar dois quadros esgota a fila de dois buffers e trava o
         * streaming. Devolver antes de pegar o proximo. */
        p4camera_release();
    }
    memset(&current, 0, sizeof(current));
    current.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    current.memory = V4L2_MEMORY_MMAP;
    if (ioctl(video_fd, VIDIOC_DQBUF, &current) != 0) {
        return ESP_FAIL;
    }
    holding_frame = true;
    if (data) *data = buffers[current.index];
    if (length) *length = current.bytesused;
    return ESP_OK;
}

/* --------------------------------- QR ----------------------------------- */

/* Reducao por 2 em cada eixo: 1280x960 -> 640x480. Um QR a 640x480 tem modulos
 * com folga de sobra para o quirc, e decodificar 1,2 milhao de pixels custaria
 * varias vezes mais por quadro sem melhorar a taxa de acerto. */
#define GRAY_DOWNSCALE 2

void p4camera_gray_size(uint16_t *width, uint16_t *height) {
    if (width) *width = gray_width;
    if (height) *height = gray_height;
}

static esp_err_t ensure_gray_buffer(void) {
    uint16_t width = frame_width / GRAY_DOWNSCALE;
    uint16_t height = frame_height / GRAY_DOWNSCALE;
    if (gray_buffer && gray_width == width && gray_height == height) {
        return ESP_OK;
    }
    free(gray_buffer);
    gray_buffer = malloc((size_t)width * height);
    if (!gray_buffer) {
        gray_width = gray_height = 0;
        return ESP_ERR_NO_MEM;
    }
    gray_width = width;
    gray_height = height;
    return ESP_OK;
}

/* RGB565 -> luminancia.
 *
 * Usamos a aproximacao inteira (2R + 5G + B) / 8 em vez dos coeficientes ITU-R
 * exatos: e uma soma e um shift por pixel, e o quirc so precisa de contraste
 * entre modulo claro e escuro, nao de fidelidade colorimetrica. */
static void rgb565_to_gray(const uint8_t *src) {
    const uint16_t *pixels = (const uint16_t *)src;
    for (uint16_t y = 0; y < gray_height; ++y) {
        const uint16_t *row = pixels + (size_t)(y * GRAY_DOWNSCALE) * frame_width;
        uint8_t *out = gray_buffer + (size_t)y * gray_width;
        for (uint16_t x = 0; x < gray_width; ++x) {
            uint16_t pixel = row[x * GRAY_DOWNSCALE];
            uint8_t r = (pixel >> 11) & 0x1f;
            uint8_t g = (pixel >> 5) & 0x3f;
            uint8_t b = pixel & 0x1f;
            /* Escalados para 8 bits: r,b sao 5 bits e g e 6. */
            out[x] = (uint8_t)(((r << 3) * 2 + (g << 2) * 5 + (b << 3)) / 8);
        }
    }
}

esp_err_t p4camera_scan(uint8_t *payload, size_t capacity, size_t *length) {
    if (length) *length = 0;
    if (video_fd < 0 || !streaming) {
        return ESP_ERR_INVALID_STATE;
    }
    if (pixel_format != V4L2_PIX_FMT_RGB565) {
        /* Formatos crus de Bayer precisariam de demosaico antes; o codigo
         * cobre so o caso que este sensor entrega de fato. */
        return ESP_ERR_NOT_SUPPORTED;
    }
    esp_err_t err = ensure_gray_buffer();
    if (err != ESP_OK) {
        return err;
    }

    uint8_t *frame = NULL;
    size_t frame_length = 0;
    err = p4camera_capture(&frame, &frame_length);
    if (err != ESP_OK) {
        return err;
    }
    rgb565_to_gray(frame);
    p4camera_release();

    k_quirc_result_t result;
    int found = k_quirc_decode_grayscale(gray_buffer, gray_width, gray_height,
        &result, 1, false);
    if (found <= 0 || !result.valid || result.data.payload_len <= 0) {
        return ESP_ERR_NOT_FOUND;
    }
    size_t n = (size_t)result.data.payload_len;
    if (n > capacity) {
        return ESP_ERR_INVALID_SIZE;
    }
    memcpy(payload, result.data.payload, n);
    if (length) *length = n;
    return ESP_OK;
}

esp_err_t p4camera_release(void) {
    if (!holding_frame) {
        return ESP_OK;
    }
    holding_frame = false;
    return ioctl(video_fd, VIDIOC_QBUF, &current) == 0 ? ESP_OK : ESP_FAIL;
}
