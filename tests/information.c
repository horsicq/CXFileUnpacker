/* Copyright (c) 2026 hors<horsicq@gmail.com>
 * SPDX-License-Identifier: MIT
 */
#include "information.h"
#include "metadata.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "line %d: %s\n", __LINE__, #condition); return 1; \
} } while (0)

static size_t occurrences(const char *text, const char *part) {
    size_t count = 0, length = strlen(part);
    while ((text = strstr(text, part)) != NULL) { ++count; text += length; }
    return count;
}

int main(void) {
    xfu_property stub[] = {{"Password", "fixture-stub-password!"},
                           {"CRC32", "12345678"}};
    xfu_property payload[] = {{"Password", "fixture payload password #2"}};
    xfu_property literal[] = {{"Password", "  p\xc3\xa4ss; \\x00\\x0A.  "},
                              {"Password source", "Embedded ADX"}};
    xfu_property empty[] = {{"Password", ""}};
    xfu_property clear[] = {{"Encrypted", "No"}};
    xfu_property duplicate[] = {{"Password", "fixture-stub-password!"},
                               {"Password #2", "fixture-stub-password!"}};
    xfu_property spaced[] = {{"Password", " fixture-stub-password!"}};
    xfu_entry entries[7] = {0};
    char *text, *retained;
    size_t i;
    for (i = 0; i < 7; ++i) {
        entries[i].name = "member.bin";
        entries[i].unpacked_size = 19;
        entries[i].packed_size = 7;
    }
    entries[0].properties = entries[1].properties = stub;
    entries[0].property_count = entries[1].property_count = 2;
    entries[2].properties = entries[3].properties = payload;
    entries[2].property_count = entries[3].property_count = 1;
    entries[4].properties = clear; entries[4].property_count = 1;

    text = xfu_information_text("delivery.exe", entries, 5, &entries[0], false);
    CHECK(text && strstr(text, "Selected: member.bin\nType: File\nSize: 19 bytes"));
    CHECK(strstr(text, "\nPassword: fixture-stub-password!"));
    CHECK(!strstr(text, "CRC32:") && !strstr(text, "Available passwords:"));
    free(text);
    text = xfu_information_text("delivery.exe", entries, 5, &entries[0], true);
    CHECK(text && strstr(text, "\nPassword: fixture-stub-password!\nCRC32: 12345678"));
    CHECK(occurrences(text, "\nPassword:") == 1);
    free(text);

    text = xfu_information_text("delivery.exe", entries, 5, NULL, false);
    CHECK(text && strstr(text, "Members: 5\n\nSelected: none\n\nAvailable passwords: 2"));
    CHECK(strstr(text, "Password: fixture-stub-password!\nMembers with this password: 2"));
    CHECK(strstr(text, "Password: fixture payload password #2\nMembers with this password: 2"));
    CHECK(!strstr(text, "CRC32:") && occurrences(text, "\nPassword:") == 2);
    free(text);

    text = xfu_information_text("clear.zip", &entries[4], 1, &entries[4], false);
    CHECK(text && !strstr(text, "Password:") && !strstr(text, "Encrypted:")); free(text);
    text = xfu_information_text("clear.zip", &entries[4], 1, NULL, true);
    CHECK(text && strstr(text, "Available passwords: none") && !strstr(text, "\nPassword:")); free(text);
    text = xfu_information_text("empty.zip", NULL, 0, NULL, false);
    CHECK(text && strstr(text, "Members: 0") && strstr(text, "Available passwords: none")); free(text);

    entries[0].properties = literal; entries[0].property_count = 2;
    text = xfu_information_text("literal.zip", entries, 1, &entries[0], false);
    CHECK(text && strstr(text, "\nPassword:   p\xc3\xa4ss; \\x00\\x0A.  "));
    CHECK(!strstr(text, "Password source:"));
    retained = text;
    entries[0].properties = empty; entries[0].property_count = 1;
    CHECK(strstr(retained, "p\xc3\xa4ss; \\x00\\x0A.  ")); free(retained);
    text = xfu_information_text("empty-password.zip", entries, 1, &entries[0], false);
    CHECK(text && !strcmp(strstr(text, "\nPassword:"), "\nPassword: ")); free(text);

    entries[0].properties = literal; entries[0].property_count = 2;
    entries[1].properties = empty; entries[1].property_count = 1;
    entries[2].properties = duplicate; entries[2].property_count = 2;
    entries[3].properties = stub; entries[3].property_count = 2;
    text = xfu_information_text("literal.zip", entries, 4, NULL, false);
    CHECK(text && strstr(text, "Available passwords: 3"));
    CHECK(strstr(text, "Password: \nMembers with this password: 1"));
    CHECK(strstr(text, "Password:   p\xc3\xa4ss; \\x00\\x0A.  \nMembers with this password: 1"));
    CHECK(strstr(text, "Password: fixture-stub-password!\nMembers with this password: 2"));
    CHECK(occurrences(text, "\nPassword:") == 3); free(text);

    entries[0].properties = stub; entries[0].property_count = 2;
    entries[1].properties = spaced; entries[1].property_count = 1;
    text = xfu_information_text("exact-groups.zip", entries, 2, NULL, false);
    CHECK(text && strstr(text, "Available passwords: 2"));
    CHECK(strstr(text, "Password:  fixture-stub-password!\nMembers with this password: 1"));
    CHECK(strstr(text, "Password: fixture-stub-password!\nMembers with this password: 1")); free(text);

    {
        char large[8192];
        xfu_property long_value = {"Password", large};
        memset(large, 'p', sizeof(large) - 1); large[sizeof(large) - 1] = 0;
        entries[0].properties = &long_value; entries[0].property_count = 1;
        text = xfu_information_text("long.zip", entries, 1, &entries[0], false);
        CHECK(text && strstr(text, large) && strlen(text) > sizeof(large));
        /* The dialog text survives mutation/destruction of borrowed metadata. */
        memset(large, 'q', sizeof(large) - 1);
        CHECK(strstr(text, "\nPassword: ppppp") && !strstr(text, "\nPassword: qqqqq")); free(text);
    }

    {
        xx_archive_record records[2];
        xfu_entry passwords[2] = {0};
        xfu_property *properties[2] = {NULL, NULL};
        size_t counts[2] = {0, 0};
        /* Distinct credentials must not collide after display escaping:
         * a raw newline and the literal four characters backslash-x0A. */
        const char *values[] = {"a\nb", "a\\x0Ab"};
        for (i = 0; i < 2; ++i) {
            xx_archive_record_init(&records[i]);
            CHECK(xx_archive_record_set_meta_str(&records[i], XX_META_ID_PASSWORD, values[i]));
            CHECK(xfu_record_properties(&records[i], false, &properties[i], &counts[i]));
            xx_archive_record_cleanup(&records[i]);
            passwords[i].name = "member.bin";
            passwords[i].properties = properties[i];
            passwords[i].property_count = counts[i];
        }
        text = xfu_information_text("distinct-passwords.zip", passwords, 2, NULL, false);
        CHECK(text && strstr(text, "Available passwords: 2"));
        CHECK(strstr(text, "Password: a\\x0Ab\nMembers with this password: 1"));
        CHECK(strstr(text, "Password: a\\\\x0Ab\nMembers with this password: 1"));
        CHECK(occurrences(text, "\nPassword:") == 2);
        free(text);
        for (i = 0; i < 2; ++i) xfu_free_properties(properties[i], counts[i]);
    }

    CHECK(!xfu_information_text(NULL, NULL, 0, NULL, false));
    CHECK(!xfu_information_text("invalid.zip", NULL, 1, NULL, false));
    entries[0].properties = NULL; entries[0].property_count = 1;
    CHECK(!xfu_information_text("invalid.zip", entries, 1, NULL, false));
    CHECK(!xfu_information_text("invalid.zip", entries, 1, &entries[0], false));
    puts("Information: selected password, Advanced metadata, exact values and archive groups passed");
    return 0;
}
