# SPDX-License-Identifier: GPL-3.0-or-later
# LuxLibre firmware, ESP32-C3 port (ESP-IDF 5.x):
#   idf.py set-target esp32c3
#   idf.py -DLX_BOARD=flashka-keychain-v05 build flash monitor
cmake_minimum_required(VERSION 3.16)
if(NOT DEFINED LX_BOARD)
    set(LX_BOARD flashka-keychain-v05)
endif()
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(luxlibre)
