/* Regression coverage for gzip payloads in UPX executable carriers. */
#include <xxfclib/formats/sfx_gzip/xx_sfx_gzip.h>
#include <xxfclib/io/xx_io.h>
#include <stdio.h>
#include <string.h>

static const unsigned char gzip_payload[] = {
    0x1f,0x8b,0x08,0x00,0x00,0x00,0x00,0x00,0x02,0xff,
    0x73,0x0c,0x72,0x36,0x54,0x48,0xaf,0xca,0x2c,0x50,
    0x28,0x4a,0x4d,0x2f,0x4a,0x2d,0x2e,0xce,0xcc,0xcf,
    0xe3,0x02,0x00,0xa3,0x3a,0x93,0xff,0x15,0x00,0x00,0x00
};

static void put16(unsigned char *p, unsigned value) {
    p[0]=(unsigned char)value; p[1]=(unsigned char)(value>>8);
}
static void put32(unsigned char *p, unsigned value) {
    put16(p,value); put16(p+2,value>>16);
}

static bool check(unsigned char *data, size_t size, bool expected) {
    xx_io_device *device=xx_io_mem_open_ro(data,size);
    xx_sfx_gzip reader;
    bool valid,okay;
    if(!device) return false;
    xx_sfx_gzip_init(&reader,device,0);
    valid=xx_sfx_gzip_check_is_valid(&reader.format,NULL);
    okay=valid==expected;
    if(valid) {
        xx_archive_record_state *state;
        const xx_archive_record *record;
        okay=okay && xx_sfx_gzip_handle_base_info(&reader.format,NULL) &&
            reader.format.format_size==1024+(int64_t)sizeof(gzip_payload) &&
            reader.format.number_of_archive_records==1;
        state=xx_format_create_archive_records_reading(&reader.format,NULL,NULL);
        record=state ? xx_format_get_current_archive_record(&reader.format,state) : NULL;
        okay=okay && record && record->data_offset==1024 &&
            record->compressed_size==sizeof(gzip_payload) &&
            xx_format_unpack_current_archive_record(&reader.format,state,NULL);
        if(state) xx_format_free_archive_records_reading(&reader.format,state);
    }
    xx_sfx_gzip_destroy(&reader);
    xx_io_close(device);
    return okay;
}

int main(void) {
    unsigned char data[1024+sizeof(gzip_payload)+7]={0};
    bool okay=true;
    memcpy(data,"MZ",2);
    put16(data+4,2); put16(data+8,4); put16(data+24,64);
    put32(data+60,128);
    memcpy(data+128,"PE\0\0",4);
    put16(data+134,1); put16(data+148,224);
    put16(data+152,0x10b); put32(data+212,512);
    memcpy(data+376,"UPX1",4);
    put32(data+392,512); put32(data+396,512);
    memcpy(data+1024,gzip_payload,sizeof(gzip_payload));
    /* Ordinary PE with a complete gzip and harmless suffix. */
    okay=check(data,sizeof(data),true) && okay;
    /* UPX's oversized SizeOfHeaders fails strict PE carrier validation. */
    put32(data+212,4096);
    okay=check(data,sizeof(data),true) && okay;
    /* A signature, a truncated stream, bad CRC and bad ISIZE cannot win. */
    okay=check(data,1024+sizeof(gzip_payload)-1,false) && okay;
    data[1024+sizeof(gzip_payload)-8]^=1;
    okay=check(data,sizeof(data),false) && okay;
    data[1024+sizeof(gzip_payload)-8]^=1;
    data[1024+sizeof(gzip_payload)-4]^=1;
    okay=check(data,sizeof(data),false) && okay;
    data[1024+sizeof(gzip_payload)-4]^=1;
    put16(data+4,0);
    okay=check(data,sizeof(data),false) && okay;
    if(!okay) fprintf(stderr,"SFX gzip regression failed\n");
    return okay ? 0 : 1;
}
