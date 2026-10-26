/* SPDX-License-Identifier: MIT */
#include <xxfclib/formats/xx_format.h>
#include <xxfclib/formats/executable/pe/xx_pe.h>
#include <xxfclib/formats/executable/executable_overlay/xx_executable_overlay.h>
#include <xxfclib/formats/archive/zip/xx_zip.h>
#include <xxfclib/io/xx_io.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); return 1; \
} } while (0)

typedef struct input {
    unsigned char *bytes;
    size_t size;
    xx_io_device *device;
} input;

static int fixture_path(char *path, size_t capacity, const char *root, const char *name)
{
    int size = snprintf(path, capacity, "%s/%s", root, name);
    return size > 0 && (size_t)size < capacity;
}

static int open_memory(input *in, const char *root, const char *name)
{
    char path[4096];
    FILE *file;
    long size;
    memset(in, 0, sizeof(*in));
    if (!fixture_path(path, sizeof(path), root, name) || !(file = fopen(path, "rb"))) return 0;
    if (fseek(file, 0, SEEK_END) || (size = ftell(file)) < 0 || fseek(file, 0, SEEK_SET)) { fclose(file); return 0; }
    in->size = (size_t)size;
    in->bytes = (unsigned char *)malloc(in->size ? in->size : 1U);
    if (!in->bytes || fread(in->bytes, 1, in->size, file) != in->size) { fclose(file); free(in->bytes); return 0; }
    fclose(file);
    in->device = xx_io_mem_open_ro(in->bytes, in->size);
    if (!in->device) { free(in->bytes); return 0; }
    return 1;
}

static void close_memory(input *in)
{
    xx_io_close(in->device);
    free(in->bytes);
    memset(in, 0, sizeof(*in));
}

static int has(const xx_list_t *types, xx_handle_type_t type)
{
    return xx_list_contains(types, &type, NULL);
}

static int valid_handle_list(const xx_list_t *types)
{
    size_t i, j;
    if (!types || types->elem_size != sizeof(xx_handle_type_t)) return 0;
    for (i = 0; i < xx_list_count(types); ++i) {
        xx_handle_type_t type = *(const xx_handle_type_t *)xx_list_at(types, i);
        if (type == XX_HANDLE_TYPE_UNKNOWN || xx_format_handle_type_file_type(type) == XX_FILE_TYPE_UNKNOWN) return 0;
        for (j = 0; j < i; ++j)
            if (*(const xx_handle_type_t *)xx_list_at(types, j) == type) return 0;
    }
    return 1;
}

static int check_catalog_identities(void)
{
    static const struct {
        xx_handle_type_t handle;
        xx_file_type_t file_type;
        const char *name;
    } identities[] = {
#define XX_UNPACK_HANDLE(name, value, type, carrier) {XX_HANDLE_TYPE_##name, XX_FILE_TYPE_##type, #name},
#include <xxfclib/formats/xx_format_unpack_handle_rows.inc>
#undef XX_UNPACK_HANDLE
    };
    size_t i, j;
    for (i = 0; i < sizeof(identities) / sizeof(identities[0]); ++i) {
        CHECK(xx_format_handle_type_file_type(identities[i].handle) == identities[i].file_type);
        CHECK(strcmp(xx_format_handle_type_to_string(identities[i].handle), identities[i].name) == 0);
        for (j = 0; j < i; ++j) CHECK(identities[j].handle != identities[i].handle);
    }
    return 0;
}

static int check_detect(const char *root, const char *name, bool deep,
                        xx_handle_type_t required, bool empty)
{
    input in;
    xx_list_t *types;
    int64_t position;
    CHECK(open_memory(&in, root, name));
    position = in.size > 7U ? 7 : 0;
    CHECK(xx_io_seek64(in.device, position, SEEK_SET) == 0);
    types = xx_format_get_unpack_handle_types_device(in.device, deep);
    CHECK(valid_handle_list(types));
    CHECK(xx_io_tell(in.device) == position);
    if (empty) CHECK(xx_list_count(types) == 0U);
    if (required != XX_HANDLE_TYPE_UNKNOWN) CHECK(has(types, required));
    xx_list_destroy(types);
    close_memory(&in);
    return 0;
}

static int check_stream_and_suffix(const char *root)
{
    char path[4096];
    input in;
    xx_io_device *named;
    xx_list_t *types;
    CHECK(open_memory(&in, root, "payload.tar.gz"));
    CHECK(xx_io_seek64(in.device, 9, SEEK_SET) == 0);
    types = xx_format_get_unpack_handle_types_device(in.device, false);
    CHECK(valid_handle_list(types));
    CHECK(has(types, XX_HANDLE_TYPE_GZ) && has(types, XX_HANDLE_TYPE_TAR_GZ));
    CHECK(xx_io_tell(in.device) == 9);
    xx_list_destroy(types);
    close_memory(&in);

    CHECK(fixture_path(path, sizeof(path), root, "magic-wrong.zip"));
    CHECK((named = xx_io_file_open(path, "rb")) != NULL);
    CHECK(xx_io_seek64(named, 11, SEEK_SET) == 0);
    types = xx_format_get_unpack_handle_types_device(named, false);
    CHECK(valid_handle_list(types));
    CHECK(has(types, XX_HANDLE_TYPE_GZ) && has(types, XX_HANDLE_TYPE_TAR_GZ));
    CHECK(!has(types, XX_HANDLE_TYPE_ZIP));
    CHECK(xx_io_tell(named) == 11);
    xx_list_destroy(types);
    CHECK(xx_io_close(named) == 0);
    return 0;
}

static int check_native_reader(const char *root, const char *name,
                               xx_file_type_t file_type, xx_handle_type_t handle)
{
    input in;
    Abstractformat *reader;
    CHECK(open_memory(&in, root, name));
    CHECK((reader = xx_format_create_reader(file_type, in.device, 0)) != NULL);
    CHECK(xx_format_is_valid(reader, NULL));
    CHECK(xx_format_handle_base_info(reader, NULL));
    CHECK(reader->file_type == file_type);
    CHECK(reader->handle_type == handle && reader->handle_type != XX_HANDLE_TYPE_UNKNOWN);
    CHECK(xx_format_get_handle_type(reader) == handle);
    xx_format_free_reader(reader);
    close_memory(&in);
    return 0;
}

static int check_prefixed_zip(const char *root)
{
    static const char expected[] = "zip member\n";
    char path[4096], decoded[sizeof(expected)] = {0};
    input in;
    xx_io_device *named, *destination;
    xx_list_t *types;
    Abstractformat *reader;
    xx_archive_record_state *state;
    const xx_archive_record *record;
    CHECK(fixture_path(path, sizeof(path), root, "prefixed.zip"));
    CHECK((named = xx_io_file_open(path, "rb")) != NULL);
    CHECK(xx_io_seek64(named, 5, SEEK_SET) == 0);
    types = xx_format_get_unpack_handle_types_device(named, false);
    CHECK(valid_handle_list(types) && has(types, XX_HANDLE_TYPE_ZIP));
    CHECK(xx_io_tell(named) == 5);
    xx_list_destroy(types);
    CHECK(xx_io_close(named) == 0);
    CHECK(check_detect(root, "prefixed.bin", false, XX_HANDLE_TYPE_UNKNOWN, true) == 0);
    CHECK(check_detect(root, "prefixed.bin", true, XX_HANDLE_TYPE_ZIP, false) == 0);

    CHECK(open_memory(&in, root, "prefixed.bin"));
    /* Physical identification stays strict. An unpack handle deliberately
     * enables the native reader's authenticated leading-data support. */
    CHECK((reader = xx_format_create_reader(XX_FILE_TYPE_ZIP, in.device, 0)) != NULL);
    CHECK(!xx_format_is_valid(reader, NULL));
    xx_format_free_reader(reader);
    CHECK((reader = xx_format_create_handle_reader(XX_HANDLE_TYPE_ZIP, in.device, 0)) != NULL);
    CHECK(xx_format_is_valid(reader, NULL));
    CHECK(xx_format_handle_base_info(reader, NULL));
    CHECK(reader->handle_type == XX_HANDLE_TYPE_ZIP);
    CHECK((state = xx_format_create_archive_records_reading(reader, NULL, NULL)) != NULL);
    CHECK((record = xx_format_get_current_archive_record(reader, state)) != NULL);
    CHECK((xx_archive_record_get_original_name(record) &&
           strcmp(xx_archive_record_get_original_name(record), "payload.txt") == 0) ||
          (xx_archive_record_get_original_name_w(record) &&
           wcscmp(xx_archive_record_get_original_name_w(record), L"payload.txt") == 0));
    CHECK((destination = xx_io_mem_open(decoded, sizeof(decoded))) != NULL);
    CHECK(xx_zip_unpack_current_archive_record_to_device(reader, state, destination, NULL));
    CHECK(xx_io_tell(destination) == (int64_t)(sizeof(expected) - 1U));
    CHECK(memcmp(decoded, expected, sizeof(expected) - 1U) == 0);
    CHECK(xx_io_close(destination) == 0);
    xx_format_free_archive_records_reading(reader, state);
    xx_format_free_reader(reader);
    close_memory(&in);
    return 0;
}

static int check_named_empty(const char *root, const char *name)
{
    char path[4096];
    xx_io_device *device;
    xx_list_t *types;
    CHECK(fixture_path(path, sizeof(path), root, name));
    CHECK((device = xx_io_file_open(path, "rb")) != NULL);
    CHECK(xx_io_seek64(device, 3, SEEK_SET) == 0);
    types = xx_format_get_unpack_handle_types_device(device, false);
    CHECK(valid_handle_list(types) && xx_list_count(types) == 0U);
    CHECK(xx_io_tell(device) == 3);
    xx_list_destroy(types);
    CHECK(xx_io_close(device) == 0);
    return 0;
}

/* Carrier variants share a native archive reader. A requested identity must
 * not survive parsing when its carrier differs from the actual input. */
static int check_requested_carrier(const char *root, const char *name,
                                    xx_handle_type_t requested, xx_handle_type_t actual)
{
    input in;
    Abstractformat *reader;
    CHECK(open_memory(&in, root, name));
    CHECK((reader = xx_format_create_handle_reader(requested, in.device, 0)) != NULL);
    CHECK(xx_format_is_valid(reader, NULL));
    CHECK(xx_format_handle_base_info(reader, NULL));
    CHECK(reader->file_type == XX_FILE_TYPE_SFX_ZIPCENTRAL);
    CHECK(reader->handle_type == actual && actual != requested);
    CHECK(xx_format_get_handle_type(reader) == actual);
    xx_format_free_reader(reader);
    close_memory(&in);
    return 0;
}

static int check_bad_pe_carrier(const char *root)
{
    input in;
    xx_pe physical;
    xx_list_t *types;
    CHECK(open_memory(&in, root, "bad-pe-sfx.bin"));
    xx_pe_init(&physical, in.device, 0);
    CHECK(!xx_format_is_valid(&physical.format, NULL));
    xx_pe_destroy(&physical);
    CHECK(xx_io_seek64(in.device, 7, SEEK_SET) == 0);
    types = xx_format_get_unpack_handle_types_device(in.device, false);
    CHECK(valid_handle_list(types));
    CHECK(!has(types, XX_HANDLE_TYPE_PE_ZIPSFX));
    CHECK(xx_io_tell(in.device) == 7);
    xx_list_destroy(types);
    close_memory(&in);
    return 0;
}

static int check_numbered_split(const char *root)
{
    static const char *names[] = {"parts.001", "empty.001", "compressed.001"};
    size_t i;
    for (i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        char path[4096];
        xx_io_device *device;
        xx_list_t *types;
        int64_t position = i == 1U ? 0 : 3;
        CHECK(fixture_path(path, sizeof(path), root, names[i]));
        CHECK((device = xx_io_file_open(path, "rb")) != NULL);
        CHECK(xx_io_seek64(device, position, SEEK_SET) == 0);
        types = xx_format_get_unpack_handle_types_device(device, false);
        CHECK(valid_handle_list(types));
        CHECK(xx_io_tell(device) == position);
        if (i == 0U) CHECK(has(types, XX_HANDLE_TYPE_NUMBERED_SPLIT));
        else if (i == 1U) CHECK(xx_list_count(types) == 0U);
        else {
            CHECK(has(types, XX_HANDLE_TYPE_GZ) && has(types, XX_HANDLE_TYPE_TAR_GZ));
            CHECK(!has(types, XX_HANDLE_TYPE_NUMBERED_SPLIT));
        }
        xx_list_destroy(types);
        CHECK(xx_io_close(device) == 0);
    }
    return 0;
}

static int check_pe_identity(const char *root, const char *name)
{
    input in;
    xx_pe reader;
    CHECK(open_memory(&in, root, name));
    xx_pe_init(&reader, in.device, 0);
    CHECK(xx_format_is_valid(&reader.format, NULL));
    CHECK(xx_format_handle_base_info(&reader.format, NULL));
    CHECK(reader.format.file_type == XX_FILE_TYPE_PE32);
    CHECK(reader.format.handle_type == XX_HANDLE_TYPE_UNKNOWN);
    xx_pe_destroy(&reader);
    close_memory(&in);
    return 0;
}

static int check_optional_com_sfx(const char *root)
{
    input in;
    Abstractformat *reader;
    bool accepted;
    CHECK(open_memory(&in, root, "com-sfx.bin"));
    reader = xx_format_create_reader(XX_FILE_TYPE_SFX_ZIPCENTRAL, in.device, 0);
    accepted = reader && xx_format_is_valid(reader, NULL) && xx_format_handle_base_info(reader, NULL);
    if (accepted) CHECK(xx_format_get_handle_type(reader) == XX_HANDLE_TYPE_COM_ZIPSFX);
    xx_format_free_reader(reader);
    close_memory(&in);
    if (accepted) CHECK(check_detect(root, "com-sfx.bin", false, XX_HANDLE_TYPE_COM_ZIPSFX, false) == 0);
    else puts("COM ZIP SFX fixture is outside the native reader's carrier support; skipped.");
    return 0;
}

static int check_domains_and_catalog(void)
{
    xx_list_t *supported;
    size_t i;
    CHECK((uint32_t)XX_HANDLE_TYPE_GZ != (uint32_t)XX_FILE_TYPE_GZ);
    CHECK(xx_format_handle_type_file_type((xx_handle_type_t)XX_FILE_TYPE_GZ) == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_handle_type_file_type(XX_HANDLE_TYPE_GZ) == XX_FILE_TYPE_GZ);
    CHECK(xx_format_handle_type_from_file_type(XX_FILE_TYPE_GZ) == XX_HANDLE_TYPE_GZ);
    CHECK(xx_format_handle_type_from_file_type(XX_FILE_TYPE_BINARY) == XX_HANDLE_TYPE_UNKNOWN);
    CHECK(xx_format_handle_type_from_file_type(XX_FILE_TYPE_TEXT) == XX_HANDLE_TYPE_UNKNOWN);
    CHECK(xx_format_handle_type_from_file_type(XX_FILE_TYPE_PE32) == XX_HANDLE_TYPE_UNKNOWN);
    CHECK(xx_format_handle_type_file_type(XX_HANDLE_TYPE_EXECUTABLE_OVERLAY) == XX_FILE_TYPE_EXECUTABLE_OVERLAY);
    CHECK(xx_format_handle_type_from_file_type(XX_FILE_TYPE_EXECUTABLE_OVERLAY) == XX_HANDLE_TYPE_EXECUTABLE_OVERLAY);
    supported = xx_format_get_supported_unpack_handle_types();
    CHECK(valid_handle_list(supported));
    CHECK(has(supported, XX_HANDLE_TYPE_ZIP) && has(supported, XX_HANDLE_TYPE_GZ));
    CHECK(has(supported, XX_HANDLE_TYPE_EXECUTABLE_OVERLAY));
    for (i = 0; i < xx_list_count(supported); ++i) {
        xx_file_type_t type = xx_format_handle_type_file_type(*(const xx_handle_type_t *)xx_list_at(supported, i));
        CHECK(type != XX_FILE_TYPE_BINARY && type != XX_FILE_TYPE_TEXT && type != XX_FILE_TYPE_PE32 && type != XX_FILE_TYPE_PE64);
    }
    xx_list_destroy(supported);
    return 0;
}

typedef struct overlay_member {
    int64_t offset;
    int64_t size;
    const char *name_suffix;
} overlay_member;

static int ends_with(const char *name, const char *suffix)
{
    size_t name_size, suffix_size;
    if (!name || !suffix) return 0;
    name_size = strlen(name);
    suffix_size = strlen(suffix);
    return name_size >= suffix_size && !strcmp(name + name_size - suffix_size, suffix);
}

/* Copy every member through the reader's extraction implementation and compare
 * it with the exact source range. This also verifies padding/tail preservation,
 * that the host image is excluded, and that nonzero bases do not shift data. */
static int check_overlay_members_with_reader(const char *root, const char *name, int64_t base,
                                             const overlay_member *members, size_t count, bool native)
{
    input in;
    Abstractformat *reader;
    xx_archive_record_state *state;
    size_t index;
    int64_t previous_end = native ? base : 0;
    CHECK(open_memory(&in, root, name));
    /* Public factories present a sliced device with offsets starting at zero;
     * direct native constructors retain coordinates in the original device. */
    reader = native ? (Abstractformat *)xx_executable_overlay_create(in.device, base) :
                      xx_format_create_handle_reader(XX_HANDLE_TYPE_EXECUTABLE_OVERLAY, in.device, base);
    CHECK(reader != NULL);
    CHECK(xx_format_is_valid(reader, NULL));
    CHECK(xx_format_handle_base_info(reader, NULL));
    CHECK(reader->file_type == XX_FILE_TYPE_EXECUTABLE_OVERLAY && reader->is_archive);
    CHECK(xx_format_get_handle_type(reader) == XX_HANDLE_TYPE_EXECUTABLE_OVERLAY);
    CHECK(xx_format_get_number_of_archive_records(reader, NULL) == count);
    CHECK((state = xx_format_create_archive_records_reading(reader, NULL, NULL)) != NULL);
    for (index = 0; index < count; ++index) {
        const xx_archive_record *record;
        unsigned char *decoded;
        xx_io_device *destination;
        int64_t offset = (native ? base : 0) + members[index].offset;
        int64_t source_offset = base + members[index].offset;
        size_t size = (size_t)members[index].size;
        CHECK((record = xx_format_get_current_archive_record(reader, state)) != NULL);
        CHECK(ends_with(xx_archive_record_get_original_name(record), members[index].name_suffix));
        CHECK(record->data_offset == offset && record->compressed_size == members[index].size);
        CHECK(xx_archive_record_get_meta_u64(record, XX_META_ID_UNCOMPRESSED_SIZE, UINT64_MAX) == (uint64_t)size);
        CHECK(offset >= previous_end && offset >= reader->base_address && (uint64_t)offset + size <= (uint64_t)xx_io_size(reader->device));
        CHECK(source_offset >= base && (uint64_t)source_offset + size <= in.size);
        if (index) CHECK(offset == previous_end);
        CHECK((decoded = (unsigned char *)malloc(size + 1U)) != NULL);
        memset(decoded, 0xA5, size + 1U);
        CHECK((destination = xx_io_mem_open(decoded, size + 1U)) != NULL);
        CHECK(xx_executable_overlay_unpack_current_archive_record_to_device(reader, state, destination, NULL));
        CHECK(xx_io_tell(destination) == (int64_t)size);
        CHECK(memcmp(decoded, in.bytes + source_offset, size) == 0 && decoded[size] == 0xA5);
        CHECK(xx_io_close(destination) == 0);
        free(decoded);
        previous_end = offset + members[index].size;
        if (index + 1U < count) CHECK(xx_format_archive_record_move_to_next(reader, state, NULL));
    }
    CHECK(previous_end == (int64_t)in.size - (native ? 0 : base));
    CHECK(!xx_format_archive_record_move_to_next(reader, state, NULL));
    CHECK(xx_format_get_current_archive_record(reader, state) == NULL);
    xx_format_free_archive_records_reading(reader, state);
    if (native) xx_executable_overlay_free((xx_executable_overlay *)reader);
    else xx_format_free_reader(reader);
    close_memory(&in);
    return 0;
}

static int check_overlay_members(const char *root, const char *name, int64_t base,
                                  const overlay_member *members, size_t count)
{
    return check_overlay_members_with_reader(root, name, base, members, count, false);
}

static int check_no_overlay(const char *root, const char *name)
{
    input in;
    Abstractformat *reader;
    xx_list_t *types;
    CHECK(open_memory(&in, root, name));
    CHECK(xx_io_seek64(in.device, 7, SEEK_SET) == 0);
    types = xx_format_get_unpack_handle_types_device(in.device, true);
    CHECK(valid_handle_list(types) && !has(types, XX_HANDLE_TYPE_EXECUTABLE_OVERLAY));
    CHECK(xx_io_tell(in.device) == 7);
    xx_list_destroy(types);
    CHECK((reader = xx_format_create_handle_reader(XX_HANDLE_TYPE_EXECUTABLE_OVERLAY, in.device, 0)) != NULL);
    CHECK(!xx_format_is_valid(reader, NULL));
    xx_format_free_reader(reader);
    close_memory(&in);
    return 0;
}

static int check_overlay_disk_extraction(const char *root)
{
    input in;
    Abstractformat *reader;
    xx_archive_record_state *state;
    xx_list_s options;
    xx_meta meta;
    xx_io_extract_scope scope = {0};
    char destination[4096];
    size_t count = 0;
    CHECK(fixture_path(destination, sizeof(destination), root, "overlay-extracted"));
    CHECK(open_memory(&in, root, "overlay-chain.bin"));
    CHECK((reader = xx_format_create_handle_reader(XX_HANDLE_TYPE_EXECUTABLE_OVERLAY, in.device, 0)) != NULL);
    CHECK(xx_format_is_valid(reader, NULL) && xx_format_handle_base_info(reader, NULL));
    xx_list_init(&options, sizeof(xx_meta), xx_meta_free_elem);
    xx_meta_init(&meta, XX_META_ID_OPT_UNPACK_PATH);
    CHECK(xx_var_set_str(&meta.var, destination) && xx_list_append(&options, &meta));
    xx_meta_init(&meta, XX_META_ID_OPT_OVERWRITE);
    xx_var_set_bool(&meta.var, true);
    CHECK(xx_list_append(&options, &meta));
    CHECK((state = xx_format_create_archive_records_reading(reader, &options, NULL)) != NULL);
    xx_list_cleanup(&options);
    CHECK(xx_io_extract_begin(&scope, destination));
    do {
        input output;
        const xx_archive_record *record = xx_format_get_current_archive_record(reader, state);
        const char *name;
        CHECK(record != NULL && (name = xx_archive_record_get_original_name(record)) != NULL);
        CHECK(xx_format_unpack_current_archive_record(reader, state, NULL));
        CHECK(open_memory(&output, destination, name));
        CHECK(output.size == (size_t)record->compressed_size);
        CHECK(memcmp(output.bytes, in.bytes + record->data_offset, output.size) == 0);
        close_memory(&output);
        ++count;
    } while (xx_format_archive_record_move_to_next(reader, state, NULL));
    CHECK(count == 4U);
    CHECK(xx_io_extract_end(&scope));
    xx_format_free_archive_records_reading(reader, state);
    xx_format_free_reader(reader);
    close_memory(&in);
    return 0;
}

static int check_executable_overlays(const char *root)
{
    static const char *positive[] = {
        "overlay-dos.bin", "overlay-pe.bin", "overlay-ne.bin", "overlay-ne-host.bin", "overlay-padding.bin", "overlay-ff.bin",
        "overlay-chain.bin", "overlay-term.bin", "overlay-pe-certificate.bin", "overlay-pe-symbols.bin",
        "overlay-pe-debug.bin", "overlay-ne-relocations.bin", "overlay-ne-resources.bin"
    };
    static const char *negative[] = {
        "plain.exe", "overlay-hidden-mz.bin", "overlay-cut-header.bin", "overlay-overflow.bin",
        "overlay-bad-outer.bin", "overlay-bad-padding.bin", "overlay-too-much-padding.bin",
        "overlay-bad-term-number.bin", "overlay-bad-term-header.bin", "overlay-bad-ne.bin",
        "overlay-pe-certificate-data.bin"
    };
    static const overlay_member dos[] = {{512, 512, "-dos-image.exe"}};
    static const overlay_member pe[] = {{512, 1024, "-pe-image.exe"}};
    static const overlay_member ne[] = {{512, 512, "-ne-image.exe"}};
    static const overlay_member padded[] = {{512, 511, "-padding.bin"}, {1023, 1024, "-pe-image.exe"}};
    static const overlay_member ff[] = {{512, 1, "-padding.bin"}, {513, 512, "-dos-image.exe"}};
    static const overlay_member chain[] = {
        {1024, 512, "-dos-image.exe"}, {1536, 511, "-padding.bin"},
        {2047, 1024, "-pe-image.exe"}, {3071, 35, "-overlay.bin"}
    };
    static const overlay_member term[] = {{512, 62, "-overlay.bin"}};
    static const overlay_member pe_auxiliary[] = {{1040, 512, "-dos-image.exe"}};
    static const overlay_member pe_symbols[] = {{1046, 512, "-dos-image.exe"}};
    static const overlay_member ne_relocations[] = {{522, 512, "-dos-image.exe"}};
    static const overlay_member ne_resources[] = {{640, 512, "-dos-image.exe"}};
    input in;
    xx_list_t *types;
    char path[4096];
    xx_io_device *named;
    size_t i;
    /* The structural interpretation must not become a physical file type. */
    CHECK(open_memory(&in, root, "overlay-chain.bin"));
    {
        Abstractdetector *detector = xx_abstract_detector_get(XX_FILE_TYPE_EXECUTABLE_OVERLAY);
        xx_file_type_t physical = xx_format_get_file_type_device(in.device);
        CHECK(physical != XX_FILE_TYPE_EXECUTABLE_OVERLAY);
        CHECK(detector != NULL && detector->fast_detect != NULL);
        CHECK(!detector->fast_detect(in.device, 0, false));
        types = xx_format_get_unpack_handle_types_device(in.device, true);
        CHECK(valid_handle_list(types) && has(types, XX_HANDLE_TYPE_EXECUTABLE_OVERLAY));
        xx_list_destroy(types);
        CHECK(xx_format_get_file_type_device(in.device) == physical);
    }
    close_memory(&in);
    for (i = 0; i < sizeof(positive) / sizeof(positive[0]); ++i) {
        CHECK(check_detect(root, positive[i], false, XX_HANDLE_TYPE_UNKNOWN, true) == 0);
        CHECK(check_detect(root, positive[i], true, XX_HANDLE_TYPE_EXECUTABLE_OVERLAY, false) == 0);
    }
    for (i = 0; i < sizeof(negative) / sizeof(negative[0]); ++i)
        CHECK(check_no_overlay(root, negative[i]) == 0);
    CHECK(check_overlay_members(root, "overlay-dos.bin", 0, dos, 1) == 0);
    CHECK(check_overlay_members(root, "overlay-pe.bin", 0, pe, 1) == 0);
    CHECK(check_overlay_members(root, "overlay-ne.bin", 0, ne, 1) == 0);
    CHECK(check_overlay_members(root, "overlay-ne-host.bin", 0, dos, 1) == 0);
    CHECK(check_overlay_members(root, "overlay-padding.bin", 0, padded, 2) == 0);
    CHECK(check_overlay_members(root, "overlay-ff.bin", 0, ff, 2) == 0);
    CHECK(check_overlay_members(root, "overlay-chain.bin", 0, chain, 4) == 0);
    CHECK(check_overlay_members(root, "overlay-nonzero-base.bin", 17, chain, 4) == 0);
    CHECK(check_overlay_members_with_reader(root, "overlay-nonzero-base.bin", 17, chain, 4, true) == 0);
    CHECK(check_overlay_members(root, "overlay-term.bin", 0, term, 1) == 0);
    CHECK(check_overlay_members(root, "overlay-pe-certificate.bin", 0, pe_auxiliary, 1) == 0);
    CHECK(check_overlay_members(root, "overlay-pe-symbols.bin", 0, pe_symbols, 1) == 0);
    CHECK(check_overlay_members(root, "overlay-pe-debug.bin", 0, pe_auxiliary, 1) == 0);
    CHECK(check_overlay_members(root, "overlay-ne-relocations.bin", 0, ne_relocations, 1) == 0);
    CHECK(check_overlay_members(root, "overlay-ne-resources.bin", 0, ne_resources, 1) == 0);
    CHECK(check_overlay_disk_extraction(root) == 0);
    /* The .exe suffix must not enable the structural fallback in shallow mode. */
    CHECK(fixture_path(path, sizeof(path), root, "overlay.exe"));
    CHECK((named = xx_io_file_open(path, "rb")) != NULL);
    CHECK(xx_io_seek64(named, 7, SEEK_SET) == 0);
    types = xx_format_get_unpack_handle_types_device(named, false);
    CHECK(valid_handle_list(types) && xx_list_count(types) == 0U && xx_io_tell(named) == 7);
    xx_list_destroy(types);
    types = xx_format_get_unpack_handle_types_device(named, true);
    CHECK(valid_handle_list(types) && has(types, XX_HANDLE_TYPE_EXECUTABLE_OVERLAY));
    CHECK(xx_io_tell(named) == 7);
    xx_list_destroy(types);
    CHECK(xx_io_close(named) == 0);
    /* A proven ZIP SFX keeps its archive-specific interpretation in deep mode. */
    CHECK(open_memory(&in, root, "pe-sfx.bin"));
    CHECK(xx_io_seek64(in.device, 7, SEEK_SET) == 0);
    types = xx_format_get_unpack_handle_types_device(in.device, true);
    CHECK(valid_handle_list(types) && has(types, XX_HANDLE_TYPE_PE_ZIPSFX));
    CHECK(!has(types, XX_HANDLE_TYPE_EXECUTABLE_OVERLAY) && xx_io_tell(in.device) == 7);
    xx_list_destroy(types);
    close_memory(&in);
    return 0;
}

int main(int argc, char **argv)
{
    static const char *bad[] = {"garbage.bin", "cut.zip", "bad.zip", "cut.gz", "bad-png", "cut-pe.bin"};
    size_t i;
    if (argc != 2) { fprintf(stderr, "Usage: %s FIXTURE_DIRECTORY\n", argv[0]); return 2; }
    CHECK(check_catalog_identities() == 0);
    CHECK(check_domains_and_catalog() == 0);
    CHECK(check_stream_and_suffix(argv[1]) == 0);
    CHECK(check_prefixed_zip(argv[1]) == 0);
    CHECK(check_detect(argv[1], "image", false, XX_HANDLE_TYPE_PNG, false) == 0);
    CHECK(check_detect(argv[1], "v7.bin", false, XX_HANDLE_TYPE_UNKNOWN, true) == 0);
    CHECK(check_detect(argv[1], "v7.bin", true, XX_HANDLE_TYPE_TAR, false) == 0);
    CHECK(check_pe_identity(argv[1], "plain.exe") == 0);
    CHECK(check_pe_identity(argv[1], "pe-sfx.bin") == 0);
    CHECK(check_detect(argv[1], "plain.exe", false, XX_HANDLE_TYPE_UNKNOWN, true) == 0);
    CHECK(check_detect(argv[1], "pe-sfx.bin", false, XX_HANDLE_TYPE_PE_ZIPSFX, false) == 0);
    CHECK(check_detect(argv[1], "dos-sfx.bin", false, XX_HANDLE_TYPE_MSDOS_ZIPSFX, false) == 0);
    CHECK(check_requested_carrier(argv[1], "dos-sfx.bin", XX_HANDLE_TYPE_PE_ZIPSFX, XX_HANDLE_TYPE_MSDOS_ZIPSFX) == 0);
    CHECK(check_requested_carrier(argv[1], "pe-sfx.bin", XX_HANDLE_TYPE_MSDOS_ZIPSFX, XX_HANDLE_TYPE_PE_ZIPSFX) == 0);
    CHECK(check_bad_pe_carrier(argv[1]) == 0);
    CHECK(check_optional_com_sfx(argv[1]) == 0);
    CHECK(check_native_reader(argv[1], "archive.zip", XX_FILE_TYPE_ZIP, XX_HANDLE_TYPE_ZIP) == 0);
    CHECK(check_native_reader(argv[1], "payload.tar.gz", XX_FILE_TYPE_GZ, XX_HANDLE_TYPE_GZ) == 0);
    CHECK(check_native_reader(argv[1], "payload.tar", XX_FILE_TYPE_TAR, XX_HANDLE_TYPE_TAR) == 0);
    CHECK(check_named_empty(argv[1], "misleading.tar.gz") == 0);
    CHECK(check_named_empty(argv[1], "ordinary.txt") == 0);
    CHECK(check_detect(argv[1], "garbage.bin", true, XX_HANDLE_TYPE_UNKNOWN, true) == 0);
    CHECK(check_numbered_split(argv[1]) == 0);
    CHECK(check_executable_overlays(argv[1]) == 0);
    for (i = 0; i < sizeof(bad) / sizeof(bad[0]); ++i)
        CHECK(check_detect(argv[1], bad[i], false, XX_HANDLE_TYPE_UNKNOWN, true) == 0);
    puts("Unpack handle API tests passed.");
    return 0;
}
