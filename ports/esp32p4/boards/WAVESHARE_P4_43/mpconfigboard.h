// Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3-C
//
// Derived from the upstream ESP32_GENERIC_P4 board. The differences that
// matter are all about being an air-gapped signer: no radio, ever.

#define MICROPY_HW_BOARD_NAME "Waveshare ESP32-P4 Touch LCD 4.3-C"
#define MICROPY_HW_MCU_NAME   "ESP32-P4"

// The REPL arrives over the on-board CH343 USB-UART bridge, not native USB.
#define MICROPY_HW_ENABLE_UART_REPL (1)

// No radio. The P4 has none of its own; the companion ESP32-C6 is held in
// reset by p4board.radio_off(). Leaving these off keeps the radio stacks out
// of the firmware entirely rather than merely unused.
#define MICROPY_PY_NETWORK_WLAN (0)
#define MICROPY_PY_BLUETOOTH    (0)
#define MICROPY_PY_ESPNOW       (0)

// microSD on SDMMC. The board wires D0-D3/CLK/CMD to GPIO 39-44; the slot
// answers there (verified by probing with no card inserted). Reading and
// writing an actual card is still unverified -- see
// reports/kern-wave43-no-sdcard.md.
#define MICROPY_PY_MACHINE_SDCARD      (1)
#define MICROPY_HW_SDMMC_LDO_CHAN_ID   (4)
#define MICROPY_HW_SDMMC_DEFAULT_SLOT  (0)
#define MICROPY_HW_SDMMC_DEFAULT_WIDTH (4)

#ifndef USB_SERIAL_JTAG_PACKET_SZ_BYTES
#define USB_SERIAL_JTAG_PACKET_SZ_BYTES (64)
#endif
