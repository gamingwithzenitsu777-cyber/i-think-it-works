cmake_minimum_required(VERSION 3.16)
project(ocrp_whitelist LANGUAGES CXX)

if(NOT DEFINED SAMP_SDK_ROOT)
  message(FATAL_ERROR "Set SAMP_SDK_ROOT to the SA-MP plugin SDK directory")
endif()

add_library(ocrp_whitelist SHARED
  plugin/main.cpp
  ${SAMP_SDK_ROOT}/amxplugin.cpp
)

target_include_directories(ocrp_whitelist PRIVATE
  ${SAMP_SDK_ROOT}
  ${SAMP_SDK_ROOT}/amx
)

target_compile_definitions(ocrp_whitelist PRIVATE LINUX)
target_compile_options(ocrp_whitelist PRIVATE -fPIC -fvisibility=hidden)
target_link_libraries(ocrp_whitelist PRIVATE dl)
set_target_properties(ocrp_whitelist PROPERTIES PREFIX "" OUTPUT_NAME "ocrp_whitelist" SUFFIX ".so")
