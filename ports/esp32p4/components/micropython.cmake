# Top-level user C module list for the ESP32-P4 port.
include(${CMAKE_CURRENT_LIST_DIR}/p4board/micropython.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/secp256k1.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/uhashlib/micropython.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/lvgl_p4/micropython.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/camera_p4/micropython.cmake)
