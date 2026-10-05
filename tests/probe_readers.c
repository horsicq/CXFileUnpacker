/* Offline diagnostic: validate registered readers against a data file. */
#include "xxfc_readers.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    xx_io_device *device;
    xxfc_reader_entry *table;
    size_t i;
    if (argc < 3) {
        fprintf(stderr, "Usage: probe_readers <file> <reader-name>...\n");
        return 2;
    }
    device = xx_io_file_open(argv[1], "rb");
    if (!device) return 2;
    printf("detected=%s\n", xx_format_file_type_to_string(
        xx_format_get_file_type_device(device)));
    table = xxfc_reader_table();
    for (i = 0; i < xxfc_reader_count(); ++i) {
        int arg;
        for (arg = 2; arg < argc; ++arg) {
            xxfc_opened opened = {0};
            int valid, parsed;
            if (strcmp(argv[arg], table[i].name) != 0) continue;
            xx_io_seek64(device, 0, SEEK_SET);
            if (!xxfc_open_named(&opened, device, 0, table[i].name)) continue;
            valid = xx_format_is_valid(opened.format, NULL);
            parsed = valid && xx_format_handle_base_info(opened.format, NULL);
            printf("%s type=%s valid=%d parsed=%d archive=%d incomplete=%d\n",
                table[i].name, xx_format_file_type_to_string(opened.type),
                valid, parsed, opened.format->is_archive,
                parsed && xxfc_is_incomplete(&opened));
            xxfc_close(&opened);
        }
    }
    xx_io_close(device);
    return 0;
}
