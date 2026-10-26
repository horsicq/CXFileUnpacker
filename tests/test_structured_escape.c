/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#define main xfu_cli_embedded_main
#include "../src/cli.c"
#undef main

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); return 1; \
} } while (0)

static int check_xml_string(const char *input, const char *expected) {
    char output[128];
    size_t count;
#ifdef _WIN32
    /* The Windows CRT's tmpfile can try a drive-root file. Keep this test's
     * temporary output in CTest's writable build working directory. */
    char temporary[MAX_PATH];
    FILE *file;
    CHECK(GetTempFileNameA(".", "xfu", 0, temporary) != 0);
    file = fopen(temporary, "w+b");
#else
    FILE *file = tmpfile();
#endif
    CHECK(file != NULL);
    CHECK(xml_string(file, input) == 0);
    CHECK(fflush(file) == 0);
    CHECK(fseek(file, 0, SEEK_SET) == 0);
    count = fread(output, 1, sizeof(output) - 1, file);
    CHECK(!ferror(file));
    output[count] = '\0';
    CHECK(fclose(file) == 0);
#ifdef _WIN32
    CHECK(remove(temporary) == 0);
#endif
    CHECK(strcmp(output, expected) == 0);
    return 0;
}

int main(void) {
    CHECK(check_xml_string("bad\xef\xbf\xbe.txt", "bad&#xFFFD;.txt") == 0); /* U+FFFE */
    CHECK(check_xml_string("bad\xef\xb7\x90.txt", "bad&#xFFFD;.txt") == 0); /* U+FDD0 */
    CHECK(check_xml_string("bad\xf0\x9f\xbf\xbe.txt", "bad&#xFFFD;.txt") == 0); /* U+1FFFE */
    CHECK(check_xml_string("<&\"'>", "&lt;&amp;&quot;&apos;&gt;") == 0);
    return 0;
}
