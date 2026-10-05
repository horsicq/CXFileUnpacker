# Settings plus the small runtime/global subset needed by standalone consumers.
# Define XXFC_STATIC, add XXSETTINGS_INCLUDE_DIR, and link XXSETTINGS_LIBRARIES.
set(XXSETTINGS_INCLUDE_DIR "${XFILEUNPACKER_XXFCLIB_DIR}/include")
set(XXSETTINGS_SOURCES
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/settings/xx_settings.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/settings/xx_settings_ini.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/settings/xx_settings_value.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/settings/xx_shortcuts.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/global/xx_settings_global.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/global/xx_global.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/global/platforms/xx_global_cpu.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/xx_rt.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/xx_rt_fp.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/xx_rt_math.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/io/xx_io_memory_only.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/xx_memory.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/xx_memory_rt.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/platforms/xx_memory_sse2.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/platforms/xx_memory_avx2.c
)
if(WIN32)
    list(APPEND XXSETTINGS_SOURCES
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/settings/platforms/xx_settings_file_windows.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/settings/platforms/xx_settings_windows.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/global/platforms/xx_global_windows.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/platforms/xx_rt_windows.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/platforms/xx_memory_windows.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/strings/platforms/xx_string_windows.c
    )
    set(XXSETTINGS_LIBRARIES kernel32)
else()
    list(APPEND XXSETTINGS_SOURCES
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/settings/platforms/xx_settings_file_posix.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/global/platforms/xx_global_posix.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/platforms/xx_rt_posix.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/platforms/xx_memory_posix.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/strings/platforms/xx_string_posix.c
    )
    find_package(Threads REQUIRED)
    set(XXSETTINGS_LIBRARIES Threads::Threads m)
    if(APPLE)
        list(APPEND XXSETTINGS_SOURCES ${XFILEUNPACKER_XXFCLIB_DIR}/src/settings/platforms/xx_settings_macos.c)
        list(APPEND XXSETTINGS_LIBRARIES "-framework CoreFoundation")
    else()
        list(APPEND XXSETTINGS_SOURCES ${XFILEUNPACKER_XXFCLIB_DIR}/src/settings/platforms/xx_settings_posix.c)
    endif()
endif()
