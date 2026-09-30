set(XFILEUNPACKER_ICON_DIR "${CMAKE_CURRENT_SOURCE_DIR}/assets/icons")
if(WIN32)
    enable_language(RC)
    configure_file("${CMAKE_CURRENT_SOURCE_DIR}/packaging/Windows/application.rc.in"
        "${CMAKE_CURRENT_BINARY_DIR}/application.rc" @ONLY)
    foreach(_xfu_app IN ITEMS XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_app})
            target_sources(${_xfu_app} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/application.rc")
        endif()
    endforeach()
endif()

if(TARGET xfileunpacker_ui)
    if(APPLE)
        enable_language(OBJC)
        target_sources(xfileunpacker_ui PRIVATE src/app_icon_macos.m src/app_icon.h)
        set_source_files_properties(src/app_icon_macos.m PROPERTIES COMPILE_OPTIONS "-fno-objc-arc")
    else()
        target_sources(xfileunpacker_ui PRIVATE src/app_icon.c src/app_icon.h)
        if(UNIX AND TARGET PkgConfig::XXWIDGETS_GTK3)
            target_compile_definitions(xfileunpacker_ui PRIVATE XFU_GTK)
            target_link_libraries(xfileunpacker_ui PRIVATE PkgConfig::XXWIDGETS_GTK3)
        endif()
    endif()
endif()

if(TARGET XFileUnpackerGUI)
    if(APPLE)
        target_sources(XFileUnpackerGUI PRIVATE "${XFILEUNPACKER_ICON_DIR}/xfileunpacker.icns")
        set_source_files_properties("${XFILEUNPACKER_ICON_DIR}/xfileunpacker.icns"
            PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
        set_target_properties(XFileUnpackerGUI PROPERTIES
            MACOSX_BUNDLE TRUE
            MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/packaging/macOS/Info.plist.in"
            MACOSX_BUNDLE_ICON_FILE xfileunpacker.icns
            MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}"
            MACOSX_BUNDLE_BUNDLE_VERSION "${PROJECT_VERSION}")
    elseif(UNIX)
        include(GNUInstallDirs)
        add_custom_command(TARGET XFileUnpackerGUI POST_BUILD
            COMMAND "${CMAKE_COMMAND}" -E copy_if_different
                "${XFILEUNPACKER_ICON_DIR}/xfileunpacker-256.png"
                "$<TARGET_FILE_DIR:XFileUnpackerGUI>/xfileunpacker.png")
        install(FILES packaging/Linux/io.github.horsicq.XFileUnpacker.desktop
            DESTINATION "${CMAKE_INSTALL_DATADIR}/applications")
        foreach(_xfu_size IN ITEMS 16 24 32 48 64 128 256 512)
            install(FILES "${XFILEUNPACKER_ICON_DIR}/xfileunpacker-${_xfu_size}.png"
                DESTINATION "${CMAKE_INSTALL_DATADIR}/icons/hicolor/${_xfu_size}x${_xfu_size}/apps"
                RENAME xfileunpacker.png)
        endforeach()
        install(FILES "${XFILEUNPACKER_ICON_DIR}/xfileunpacker.svg"
            DESTINATION "${CMAKE_INSTALL_DATADIR}/icons/hicolor/scalable/apps")
    endif()
endif()
unset(_xfu_app)
unset(_xfu_size)
