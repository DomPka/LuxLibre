# SPDX-License-Identifier: GPL-3.0-or-later
set(FW ${CMAKE_CURRENT_LIST_DIR}/../../..)
idf_component_register(
    SRCS "app_main.cpp" "hal_esp32c3.cpp"
         "${FW}/core/lx_params.cpp" "${FW}/core/lx_ramp.cpp" "${FW}/core/lx_input.cpp"
         "${FW}/core/lx_thermal.cpp" "${FW}/core/lx_battery.cpp" "${FW}/core/lx_aux.cpp"
         "${FW}/core/lx_storage.cpp" "${FW}/core/lx_ui.cpp" "${FW}/core/lx_console.cpp"
         "${FW}/core/lx_light.cpp"
    INCLUDE_DIRS "${FW}/core" "${FW}/hal" "${FW}/boards/${LX_BOARD}"
    REQUIRES driver esp_adc esp_timer nvs_flash esp_system)
target_compile_options(${COMPONENT_LIB} PRIVATE -fno-exceptions -fno-rtti)
