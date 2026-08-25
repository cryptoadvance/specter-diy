# MicroPython user C module: board support for the Waveshare ESP32-P4 4.3-C.

add_library(usermod_p4board INTERFACE)

target_sources(usermod_p4board INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/modp4board.c
    ${CMAKE_CURRENT_LIST_DIR}/display.c
    ${CMAKE_CURRENT_LIST_DIR}/touch.c
    ${CMAKE_CURRENT_LIST_DIR}/radio.c
)

target_include_directories(usermod_p4board INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

# User C modules are compiled outside the IDF component graph, so the ESP-IDF
# headers they use are not on the include path by default.
#
# MicroPython flattens a usermod's INTERFACE include directories into the
# component's INCLUDE_DIRS, and the IDF then checks each entry is a real
# directory. Generator expressions therefore do not work here -- they arrive
# unexpanded and the build fails with "is not a directory". Resolve the
# components to literal paths instead.
foreach(component
    driver
    esp_driver_gpio
    esp_driver_i2c
    esp_driver_ledc
    esp_lcd
    esp_hw_support
    esp_common
    esp_rom
    esp_system
    hal
    soc
    log
    freertos
)
    idf_component_get_property(component_dir ${component} COMPONENT_DIR)
    idf_component_get_property(component_includes ${component} INCLUDE_DIRS)
    foreach(include_dir ${component_includes})
        if(IS_ABSOLUTE ${include_dir})
            set(resolved ${include_dir})
        else()
            set(resolved ${component_dir}/${include_dir})
        endif()
        if(IS_DIRECTORY ${resolved})
            target_include_directories(usermod_p4board INTERFACE ${resolved})
        endif()
    endforeach()
endforeach()

target_link_libraries(usermod INTERFACE usermod_p4board)
