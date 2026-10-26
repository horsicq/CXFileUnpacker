# Compatibility entry point for older standalone unpacker builds.
# The library owns format sources and optional stream selection.
foreach(_xfu_stream DATASTRUCTS IMPORT EXPORT RESOURCES METADATA SYMBOLS)
    set(XXFC_ENABLE_STREAM_${_xfu_stream} OFF)
endforeach()
unset(_xfu_stream)
include("${XFILEUNPACKER_XXFCLIB_DIR}/xxformats.cmake")
