/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include <xxfclib/formats/xx_format.h>
#include <xxfclib/io/xx_io.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); exit(1); } } while (0)

typedef struct counted_io {
    size_t reads, seeks, sizes, tells;
    int64_t position;
} counted_io;

static ssize_t counted_read(xx_io_device *device, void *buffer, size_t length)
{
    counted_io *counted = device->priv;
    (void)buffer; (void)length;
    ++counted->reads;
    return -1;
}

static int counted_seek64(xx_io_device *device, int64_t offset, int whence)
{
    counted_io *counted = device->priv;
    ++counted->seeks;
    if (whence != SEEK_SET) return -1;
    counted->position = offset;
    return 0;
}

static int counted_seek(xx_io_device *device, long offset, int whence)
{
    return counted_seek64(device, offset, whence);
}

static int64_t counted_size(xx_io_device *device)
{
    counted_io *counted = device->priv;
    ++counted->sizes;
    return 64;
}

static int64_t counted_tell(xx_io_device *device)
{
    counted_io *counted = device->priv;
    ++counted->tells;
    return counted->position;
}

/* One empty ustar member followed by its two terminating blocks. */
static void make_tar(unsigned char bytes[1536])
{
    unsigned int checksum = 0;
    size_t i;
    memset(bytes, 0, 1536);
    memcpy(bytes, "empty.txt", 9);
    memcpy(bytes + 100, "0000644", 7);
    memcpy(bytes + 108, "0000000", 7);
    memcpy(bytes + 116, "0000000", 7);
    memcpy(bytes + 124, "00000000000", 11);
    memcpy(bytes + 136, "00000000000", 11);
    memset(bytes + 148, ' ', 8);
    bytes[156] = '0';
    memcpy(bytes + 257, "ustar", 5);
    memcpy(bytes + 263, "00", 2);
    for (i = 0; i < 512; ++i) checksum += bytes[i];
    CHECK(snprintf((char *)bytes + 148, 7, "%06o", checksum) == 6);
    bytes[155] = ' ';
}

static void check_extensions(void)
{
    CHECK(xx_format_get_file_type_extension("archive.ZIP") == XX_FILE_TYPE_ZIP);
    CHECK(xx_format_get_file_type_extension("document.DOCX") == XX_FILE_TYPE_ZIP);
    CHECK(xx_format_get_file_type_extension("archive.tar.gz") == XX_FILE_TYPE_TAR_GZ);
    CHECK(xx_format_get_file_type_extension("C:\\some.folder\\archive.TAR.GZ") == XX_FILE_TYPE_TAR_GZ);
    CHECK(xx_format_get_file_type_extension("/some.folder/archive.ANA") == XX_FILE_TYPE_PCE_ANADISK);
    CHECK(xx_format_get_file_type_extension("disk.img") == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_get_file_type_extension(NULL) == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_get_file_type_extension("") == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_get_file_type_extension("archive") == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_get_file_type_extension("archive.") == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_get_file_type_extension("archive.no-such-format-extension") == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_get_file_type_extension("/folder.ZIP/archive") == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_get_file_type_extension("C:\\folder.ZIP\\archive") == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_get_file_type_extension("/folder.ZIP/") == XX_FILE_TYPE_UNKNOWN);
}

static void check_extension_cost(void)
{
    counted_io counted = {0};
    xx_io_device device = {0};
    counted.position = 37;
    device.priv = &counted;
    device.read = counted_read;
    device.seek = counted_seek;
    device.seek64 = counted_seek64;
    device.total_size = counted_size;
    device.tell = counted_tell;
    /* An extension is a provisional type even when the device cannot be read. */
    CHECK(xx_format_get_file_type_device_fast(&device, "invalid.ZIP") == XX_FILE_TYPE_ZIP);
    CHECK(xx_format_get_file_type_device_fast(&device, "archive.TAR.GZ") == XX_FILE_TYPE_TAR_GZ);
    CHECK(xx_format_get_file_type_device_fast(&device, "sectors.ANA") == XX_FILE_TYPE_PCE_ANADISK);
    CHECK(counted.reads == 0 && counted.seeks == 0 && counted.sizes == 0 && counted.tells == 0);
    CHECK(counted.position == 37);
    CHECK(xx_format_get_file_type_device_fast(NULL, "archive.ZIP") == XX_FILE_TYPE_UNKNOWN);
    CHECK(xx_format_get_file_type_device_fast(NULL, NULL) == XX_FILE_TYPE_UNKNOWN);
}

static void check_legacy_fallback(void)
{
    unsigned char tar[1536];
    xx_io_device *device;
    FILE *file;
    make_tar(tar);
    device = xx_io_mem_open_ro(tar, sizeof(tar));
    CHECK(device && xx_io_seek64(device, 71, SEEK_SET) == 0);
    CHECK(xx_format_get_file_type_device(device) == XX_FILE_TYPE_TAR);
    CHECK(xx_io_tell(device) == 71);
    /* The new API intentionally chooses the suffix ahead of content. */
    CHECK(xx_format_get_file_type_device_fast(device, "renamed.ZIP") == XX_FILE_TYPE_ZIP);
    CHECK(xx_io_tell(device) == 71);
    CHECK(xx_format_get_file_type_device_fast(device, "renamed.tar.gz") == XX_FILE_TYPE_TAR_GZ);
    CHECK(xx_io_tell(device) == 71);
    CHECK(xx_format_get_file_type_device(device) == XX_FILE_TYPE_TAR);
    CHECK(xx_io_tell(device) == 71);
    CHECK(xx_format_get_file_type_device_fast(device, "archive") == XX_FILE_TYPE_TAR);
    CHECK(xx_io_tell(device) == 71);
    CHECK(xx_format_get_file_type_device_fast(device, "archive.unknown-extension") == XX_FILE_TYPE_TAR);
    CHECK(xx_io_tell(device) == 71);
    CHECK(xx_format_get_file_type_device_fast(device, "ambiguous.img") == XX_FILE_TYPE_TAR);
    CHECK(xx_io_tell(device) == 71);
    CHECK(xx_format_get_file_type_device_fast(device, NULL) == XX_FILE_TYPE_TAR);
    CHECK(xx_io_tell(device) == 71);
    CHECK(xx_io_close(device) == 0);

    /* A NULL path obtains the suffix from a file-backed device's source path. */
    file = fopen("fast-detector-source.ZIP", "wb");
    CHECK(file && fwrite(tar, 1, sizeof(tar), file) == sizeof(tar));
    CHECK(fclose(file) == 0);
    device = xx_io_file_open("fast-detector-source.ZIP", "rb");
    CHECK(device && xx_io_seek64(device, 71, SEEK_SET) == 0);
    CHECK(xx_format_get_file_type_device_fast(device, NULL) == XX_FILE_TYPE_ZIP);
    CHECK(xx_io_tell(device) == 71);
    CHECK(xx_format_get_file_type_device(device) == XX_FILE_TYPE_TAR);
    CHECK(xx_io_tell(device) == 71);
    CHECK(xx_io_close(device) == 0);
    CHECK(remove("fast-detector-source.ZIP") == 0);
}

int main(void)
{
    check_extensions();
    check_extension_cost();
    check_legacy_fallback();
    puts("Extension-first detection, zero-I/O hints and legacy fallback passed");
    return 0;
}
