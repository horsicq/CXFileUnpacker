# Preserve a user's shortcut overrides when rebuilding an existing checkout.
if(NOT EXISTS "${DESTINATION}")
    file(COPY_FILE "${SOURCE}" "${DESTINATION}")
endif()
