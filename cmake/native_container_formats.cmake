# Native readers use individual format modules in the normal xxformats target.
# Ship their scope/evidence notes and the Unicode license for CAB CP932 names.
install(FILES
    "${CMAKE_CURRENT_SOURCE_DIR}/docs/NATIVE_CONTAINER_FORMATS.md"
    DESTINATION share/doc/XFileUnpacker/native-containers)
install(FILES
    "${XFILEUNPACKER_XXFCLIB_DIR}/docs/NATIVE_CONTAINER_FORMATS.md"
    DESTINATION share/doc/XFileUnpacker/native-containers
    RENAME XXFCLIB_NATIVE_CONTAINER_FORMATS.md)
install(FILES
    "${XFILEUNPACKER_XXFCLIB_DIR}/docs/STREAM_READERS_PROVENANCE.md"
    DESTINATION share/doc/XFileUnpacker/native-containers OPTIONAL)
install(FILES
    "${XFILEUNPACKER_XXFCLIB_DIR}/src/codepages/UNICODE.LICENSE"
    DESTINATION share/licenses/xxfclib
    RENAME unicode-cp932.txt)
