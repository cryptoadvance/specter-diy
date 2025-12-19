"""STM32F469 Discovery board debugging utilities."""

# OpenOCD configuration
OPENOCD_CFG = "board/stm32f469discovery.cfg"
OPENOCD_PORT = 4444
GDB_PORT = 3333

# Serial configuration
BAUD_RATE = 115200
SERIAL_BLACKLIST = [
    "004NTKF",  # LG monitor
]
