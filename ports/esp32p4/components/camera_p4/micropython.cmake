# MicroPython user C module: binding da camera.
#
# O trabalho pesado esta no componente ESP-IDF p4camera, em
# ports/esp32p4/idf_components/p4camera. Ele precisa ser um componente de
# verdade -- e nao um usermod -- porque so componentes tem idf_component.yml, e
# e assim que a dependencia gerenciada espressif/esp_video entra no build.
#
# O componente chega pela variavel EXTRA_COMPONENT_DIRS, passada em
# tools/build.sh.

add_library(usermod_camera_p4 INTERFACE)

target_sources(usermod_camera_p4 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/modcamera.c
)

target_include_directories(usermod_camera_p4 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/../../idf_components/p4camera
)

foreach(component esp_common esp_rom log freertos hal soc)
    idf_component_get_property(component_dir ${component} COMPONENT_DIR)
    idf_component_get_property(component_includes ${component} INCLUDE_DIRS)
    foreach(include_dir ${component_includes})
        if(IS_ABSOLUTE ${include_dir})
            set(resolved ${include_dir})
        else()
            set(resolved ${component_dir}/${include_dir})
        endif()
        if(IS_DIRECTORY ${resolved})
            target_include_directories(usermod_camera_p4 INTERFACE ${resolved})
        endif()
    endforeach()
endforeach()

target_link_libraries(usermod INTERFACE usermod_camera_p4)
