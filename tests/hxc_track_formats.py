"""Independent documented floppy-container byte writers and extraction checks.

These fixtures test component preservation, framing and native checksums, not
unimplemented flux-to-filesystem recovery. No archived programs are executed.
"""
import argparse
import binascii
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zlib


def pattern(size, seed=7):
    return bytes((index * 37 + seed) & 255 for index in range(size))


def ccitt(data):
    return binascii.crc_hqx(data, 0xffff)


def crc16_block(data):
    return data + struct.pack('>H', ccitt(data))


def tag(value):
    return value.encode('ascii').ljust(16, b'\0')


def extended_adf(blank=False, multi=False):
    dos, raw = pattern(512), pattern(24, 12)
    table = struct.pack('>HHII', 0, 0, len(dos), len(dos)*8)
    table += struct.pack('>HHII', 0, 0x101 if multi else 1, len(raw), 0 if blank else 64)
    header = b'UAE-1ADF' + struct.pack('>HH', 0, 2) + table
    return header+dos+raw, {'descriptor.ext-adf': header,
        'track-C000-H0.sectors': dos,
        'track-C000-H1.'+('unformatted-allocation' if blank else 'mfm-bitcells'): raw}


def old_adf():
    raw, dos = pattern(20, 9), pattern(512, 11)
    header = b'UAE--ADF'+struct.pack('>HHHH', 0x4489, len(raw), 0, len(dos))+bytes(158*4)
    return header+raw+dos, {'descriptor.old-ext-adf': header,
        'track-C000-H0.mfm-bitcells': b'\x44\x89'+raw,
        'track-C000-H1.sectors': dos}


def dim(sparse=False, start=0):
    h = bytearray(32)
    h[:2] = b'BB'; h[3] = int(sparse); h[6] = 1; h[8] = 2
    h[10] = start; h[12] = start+1; h[13] = 0
    struct.pack_into('>H', h, 14, 512)
    payload = pattern(91 if sparse else 4096)
    return bytes(h)+payload, {'descriptor.dim': bytes(h),
        'unreconstructed-used-sectors.dim' if sparse else 'sector-image.st': payload}


def stw():
    h = b'STW\0'+struct.pack('>HBBH', 0x100, 2, 2, 128)
    output, expected = h, {'descriptor.stw': h}
    for cylinder in range(2):
        for head in range(2):
            data = pattern(256, cylinder*5+head)
            output += b'TRK'+bytes((head, cylinder))+data
            expected[f'track-C{cylinder:03}-H{head}.mfm-words-be'] = data
    return output, expected


def stt(unknown=False):
    tracks, payloads, expected = [], [], {}
    for head in range(2):
        data, raw = pattern(512, head+1), b'\xa1\xa1\xa1\xfe'
        sector_end = 12+10+len(data)
        # Stored address CRC deliberately need not be valid: protected images
        # may intentionally retain bad sectors. The parser must preserve it.
        sector = bytes((0, head, 1, 2, 0x12, 0x34))+struct.pack('<HH', 22, 512)
        flags = 7 if unknown else 3
        t = b'TRCK'+struct.pack('<HHHH', flags, sector_end, 0, 1)+sector+data
        raw_end = sector_end+8+len(raw)
        t += struct.pack('<4H', raw_end, 0, sector_end+8, len(raw))+raw
        if unknown:
            t += struct.pack('<H', len(t)+4)+b'??'
        tracks.append(t)
        expected[f'C000-H{head}-sector-000-ID001.bin'] = data
        expected[f'track-C000-H{head}.raw-bytes'] = raw
        expected[f'track-C000-H{head}.original-stt'] = t
    offset = 14+12
    table = b''
    for t in tracks:
        table += struct.pack('<IH', offset, len(t)); offset += len(t)
    header = b'STEM'+struct.pack('<5H', 1, 0, 3, 1, 2)+table
    expected['descriptor.stt'] = header
    return header+b''.join(tracks), expected


def dfi(new=True):
    h = b'DFE2' if new else b'DFER'
    expected = {'descriptor.dfi': h}; out = h
    for i, body in enumerate((b'\x01\x7f\x84\x03\x7f', b'\x00\x80\x01\x02')):
        descriptor = struct.pack('>HHHI', i, i%2, 0, len(body))
        out += descriptor+body
        stem = f'capture-{i:04}-C{i:03}-H{i%2}-S0'
        expected[stem+'.descriptor.dfi'] = descriptor
        expected[stem+('.dfe2-flux' if new else '.dfer-flux')] = body
    return out, expected


def qd():
    output = bytearray(2048)
    output[:40] = b'HXCQDDRV'+struct.pack('<8I', 0, 1, 2, 0, 1, 200000, 0, 512)
    expected = {}
    for i in range(2):
        struct.pack_into('<4I', output, 512+i*16, 1024+i*512, 512, 0, 512)
        body = pattern(512, i)
        output[1024+i*512:1536+i*512] = body
        expected[f'disk-000-side-{i}.lsb-bitcells'] = body
    expected['descriptor.qd'] = bytes(output[:544])
    return bytes(output), expected


def sdu():
    header = struct.pack('<21s5s10H', b'SAB Diskette Utility\0', b'1.00\0',
        0, 0, 2, 2, 2, 0, 0, 1, 512, 1024)
    data = pattern(4096)
    return header+data, {'descriptor.sdu': header, 'sector-image.img': data}


def oric(raw=True, geometry=1):
    h = (b'MFM_DISK' if raw else b'ORICDISK')+struct.pack('<3I', 2, 2, geometry if raw else 2)+bytes(236)
    expected, output = {'descriptor.oric-dsk': h}, h
    for i in range(4):
        data = pattern(6400 if raw else 512, i)
        cylinder, head = (i//2, i%2) if raw and geometry==2 else (i%2, i//2)
        expected[f'track-C{cylinder:03}-H{head}.'+('decoded-mfm-bytes' if raw else 'sectors')] = data
        output += data
    return output, expected


def lz4_literal(data):
    size = len(data)
    result = bytes((min(size, 15)<<4,))
    if size>=15:
        n = size-15
        while n>=255:
            result += b'\xff'; n -= 255
        result += bytes((n,))
    return result+data


def stream(nonzero_padding=True, packets=2, empty=False):
    output, expected = b'', {}
    for number in range(packets):
        meta = b'format_version v1.0\nsample_rate_hz 25000000\n\0'
        meta = meta.ljust((len(meta)+3)&~3, b'\0')
        flux = b'' if empty else b'\x05\x80\xc8\xc0\x01\x02\xe0\x00\x03\x04\x00'
        io = pattern(12, number)
        blocks = struct.pack('<II', 0, len(meta))+meta
        for type_, plain, pulses in ((2, flux, 0 if empty else 4), (1, io, None)):
            packed = lz4_literal(plain)
            trailer = bytes((0xa5 if nonzero_padding else 0,))*((-len(packed))%4)
            fields = struct.pack('<II', len(packed), len(plain))
            if pulses is not None: fields += struct.pack('<I', pulses)
            payload = fields+packed+trailer
            blocks += struct.pack('<II', type_, len(payload))+payload
        header = b'CHKH'+struct.pack('<II', 12+len(blocks)+4, number)
        packet = header+blocks
        packet += struct.pack('<I', zlib.crc32(packet, 0xffffffff))
        output += packet
        expected[f'packet-{number:04}.original.hxcstream'] = packet
        expected[f'packet-{number:04}-metadata.bin'] = meta
        expected[f'packet-{number:04}-block-02.flux-delta-encoded'] = flux
        expected[f'packet-{number:04}-block-03.io-u16le'] = io
    return output, expected


def afi(compressed=True, reserved=False, strings=False):
    count = 2
    list_size = 22+count*4
    list_offset = 32
    out = bytearray(bytes(32+list_size))
    expected, offsets = {}, []
    for head in range(count):
        a = len(out); offsets.append(a-list_offset)
        payload = pattern(32, head+3)
        packed = zlib.compress(payload) if compressed else payload
        packer = 2 if reserved else int(compressed)
        descriptor = tag('TRACK')+struct.pack('<5I', 0, head, 3, 256, 1)+struct.pack('<I', 42)
        descriptor = crc16_block(descriptor)
        block = tag('TRACKDATA')+struct.pack('<I', 6)+tag('CELL_DATA')
        block += struct.pack('<4I', 1, len(packed), packer, len(payload))
        block = crc16_block(block+packed)
        out += descriptor+block
        expected[f'track-C000-H{head}.descriptor.afi'] = descriptor
        expected[f'C000-H{head}-block-00.original.afi'] = block
        expected[f'C000-H{head}-block-00-CELL_DATA.'+('unsupported-packed-bytes' if reserved else 'decoded-bytes')] = packed if reserved else payload
    info_offset = len(out)
    info = tag('AFI_INFO')+struct.pack('<9I', 0, 1, 2, count, 0, 0, 0, 1, int(strings))
    if strings: info += struct.pack('<I', 58)
    info = crc16_block(info)
    expected['floppy-info.afi'] = info
    out += info
    if strings:
        string = crc16_block(tag('STRING')+tag('DISC_TITLE')+struct.pack('<I', 9)+b'Example!\0')
        expected['string-000.original.afi'] = string
        out += string
    directory = crc16_block(tag('TRACKLIST')+struct.pack('<I', count)+struct.pack('<2I', *offsets))
    out[list_offset:list_offset+list_size] = directory
    header = crc16_block(tag('AFI_FLOPPY_IMG')+bytes((0, 2))+struct.pack('<3I', 32, info_offset, list_offset))
    out[:32] = header
    expected['descriptor.afi'] = header; expected['track-index.afi'] = directory
    return bytes(out), expected


def svd(version='2.0', type_=1):
    sectors, tracks, sides = 2, 2, 2 if version=='2.0' else 1
    header = f'{version}\n{sectors}\n{tracks}\n'.encode()
    if version=='2.0': header += f'{sides}\n1\n0\n'.encode()
    out, expected = header, {'descriptor.svd': header}
    for i in range(tracks*sides):
        index = bytearray(256)
        for sector in range(sectors):
            if version=='1.2': index[sector*9:sector*9+9] = bytes((i//sides, i%sides, sector+1, 1, 0x12, 0x34, 0xfb, 0x56, 0x78))
            elif type_==1: index[sector*10:sector*10+10] = bytes((1, i//sides, i%sides, sector+1, 1, 0x12, 0x34, 0xfb, 0x56, 0x78))
            elif type_==16: index[sector*15] = 16
            elif type_==64: index[0 if sector==0 else 5] = 64
            else: raise ValueError(type_)
        original = [pattern(256, 11+i*3+sector) for sector in range(sectors)]
        stored = b''
        for sector, data in enumerate(original):
            rotation = (7+sector*9) if version=='1.2' else (8+sector*10)
            stored += data[-rotation:]+data[:-rotation]
        out += bytes(index)+stored
        stem = f'track-C{i//sides:03}-H{i%sides}'
        expected[stem+'.descriptor.svd'] = bytes(index)
        expected[stem+'.stored-blocks.svd'] = stored
        if type_==1: expected[stem+'.wd-sectors'] = b''.join(original)
    return out, expected


def mfm_byte(value, previous=0):
    bits = ''
    for bit in range(7, -1, -1):
        data = (value>>bit)&1
        bits += str(int(not(previous or data)))+str(data); previous = data
    return bits, previous


def fei(track_bytes=12500):
    out, expected = b'', {}
    for head in range(2):
        for cylinder in range(2):
            info = bytes((0xa1, 0xa1, 0xa1, 0xfe, cylinder, head, 1, 2))
            tail = bytes((0xfe, cylinder, head, 1, 2))+struct.pack('>H', ccitt(info))
            bits, previous = '0100010010001001'*3, 1
            for byte in tail:
                encoded, previous = mfm_byte(byte, previous); bits += encoded
            raw = bytes(int(bits[i:i+8][::-1], 2) for i in range(0, len(bits), 8))
            raw = raw.ljust(track_bytes, b'\0')
            out += raw; expected[f'track-C{cylinder:03}-H{head}.lsb-mfm-bitcells'] = raw
    return out, expected


def a2r(slvd_entries=2, version=2, empty=False, mixed=False, large=False):
    header = b'A2R3\xff\x0a\x0d\x0a'
    info = b'\x01'+b'Independent fixture'.ljust(32, b' ')+bytes((5, 0, 1, 0))
    def chunk(tag_, body): return tag_+struct.pack('<I', len(body))+body
    output = header+chunk(b'INFO', info)
    expected = {'capture-info.bin': info}
    slvd = bytes((version,))+struct.pack('<I', 62500)+bytes(11)
    for loc in range(0 if empty else slvd_entries):
        data = bytes((64,))*600000 if large else bytes((20, 255, 1, 30+loc))
        descriptor = b'T'+struct.pack('<H', loc)+bytes((0, 0))+bytes(6)+b'\x02'+struct.pack('<2I', 0, 50)+struct.pack('<I', len(data))
        slvd += descriptor+data
        expected[f'solved-{loc:04}-{loc:03}.descriptor.bin'] = descriptor
        expected[f'solved-{loc:04}-{loc:03}.flux'] = data
    slvd += b'X'; output += chunk(b'SLVD', slvd)
    expected['slvd-0000-header.bin'] = slvd[:16]
    if mixed:
        flux = b'\x40\x40\x40'
        descriptor = b'C'+bytes((1,))+struct.pack('<H', 3)+b'\x01'+struct.pack('<II', 100, len(flux))
        rwcp_header = b'\x01'+struct.pack('<I', 62500)+bytes(11)
        output += chunk(b'RWCP', rwcp_header+descriptor+flux+b'X')
        expected['rwcp-0000-header.bin'] = rwcp_header
        expected['capture-0000-003.descriptor.bin'] = descriptor
        expected['capture-0000-003.flux'] = flux
    return output, expected


def altered(data, offset, value):
    result = bytearray(data); result[offset] = value; return bytes(result)


def afi_authenticated_mutation(data, *, adler=False, wrong_size=False):
    result = bytearray(data)
    directory = struct.unpack_from('<I', result, 26)[0]
    track = directory+struct.unpack_from('<I', result, directory+20)[0]
    block = track+struct.unpack_from('<I', result, track+36)[0]
    packed = struct.unpack_from('<I', result, block+40)[0]
    end = block+52+packed
    if adler: result[end-1] ^= 1
    if wrong_size:
        size = struct.unpack_from('<I', result, block+48)[0]
        struct.pack_into('<I', result, block+48, size+1)
    result[end:end+2] = struct.pack('>H', ccitt(result[block:end]))
    return bytes(result)


def stream_authenticated_mutation(data, *, pulses=False, wrong_size=False, lz4=False, duplicate=False):
    result = bytearray(data)
    packet_size = struct.unpack_from('<I', result, 4)[0]
    block = 12+8+struct.unpack_from('<I', result, 16)[0]
    if pulses: struct.pack_into('<I', result, block+16, 3)
    if wrong_size:
        size = struct.unpack_from('<I', result, block+12)[0]
        struct.pack_into('<I', result, block+12, size+1)
    if lz4: result[block+20] = 0xff
    result[packet_size-4:packet_size] = struct.pack('<I', zlib.crc32(result[:packet_size-4], 0xffffffff))
    if duplicate:
        second = packet_size
        struct.pack_into('<I', result, second+8, 0)
        size = struct.unpack_from('<I', result, second+4)[0]
        result[second+size-4:second+size] = struct.pack('<I', zlib.crc32(result[second:second+size-4], 0xffffffff))
    return bytes(result)


def run_case(executable, probe, folder, name, reader, data, expected, lifecycle=None):
    source, output = folder/(name+'.bin'), folder/(name+'-output')
    source.write_bytes(data)
    if probe:
        process = subprocess.run([str(probe), str(source), reader], capture_output=True, timeout=30)
        message = process.stdout.decode('utf-8', 'replace')
        line = next((line for line in message.splitlines() if line.startswith(reader+' ')), '')
        assert line, (name, 'reader not registered', message)
        assert ('valid=1 parsed=1' in line)==(expected is not None), (name, line)
    process = subprocess.run([str(executable), 'x', str(source), '-o'+str(output)],
        capture_output=True, timeout=30, cwd=folder)
    diagnostic = (process.stdout+process.stderr).decode('utf-8', 'replace')
    files = {re.sub(r'^\d{4}-', '', p.name): p.read_bytes()
        for p in output.rglob('*') if p.is_file()} if output.exists() else {}
    if expected is None:
        assert process.returncode!=0 and not files, (name, 'malformed accepted', diagnostic, files.keys())
    else:
        assert process.returncode==0, (name, process.returncode, diagnostic)
        if reader=='apple_a2r':
            assert files==expected, (name, files.keys(), expected.keys(), diagnostic)
        else:
            info = files.pop('container-info.txt', None)
            assert info and b'Representation:' in info and b'Integrity:' in info, (name, info)
            assert files==expected, (name, files.keys(), expected.keys(), diagnostic)
        if lifecycle:
            verified = subprocess.run([str(lifecycle), str(source), reader],
                capture_output=True, timeout=30)
            assert verified.returncode==0, (name, 'lifecycle', verified.stdout, verified.stderr)
    print(name+': passed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unpacker', required=True, type=Path)
    parser.add_argument('--probe', type=Path)
    parser.add_argument('--lifecycle-probe', type=Path)
    args = parser.parse_args()
    executable = args.unpacker.resolve(); probe = args.probe.resolve() if args.probe else None
    lifecycle = args.lifecycle_probe.resolve() if args.lifecycle_probe else None
    cases = []
    def good(name, reader, writer, *a, **kw):
        data, expected = writer(*a, **kw); cases.append((name, reader, data, expected)); return data
    def bad(name, reader, data): cases.append((name, reader, data, None))
    adf = good('ext-adf', 'amiga_ext_adf', extended_adf)
    good('ext-adf-unformatted', 'amiga_ext_adf', extended_adf, blank=True)
    good('ext-adf-revolutions', 'amiga_ext_adf', extended_adf, multi=True)
    old = good('old-ext-adf', 'amiga_old_ext_adf', old_adf)
    di = good('dim-complete', 'atari_dim', dim)
    good('dim-sparse-preserved', 'atari_dim', dim, sparse=True)
    good('dim-partial-cylinder-range', 'atari_dim', dim, start=17)
    sw = good('stw', 'atari_stw', stw)
    st = good('stt-sector-raw', 'atari_stt', stt)
    good('stt-unknown-section', 'atari_stt', stt, unknown=True)
    df = good('dfi-new-terminal-carry', 'discferret_dfi', dfi)
    good('dfi-old-carry', 'discferret_dfi', dfi, new=False)
    qu = good('quickdisk', 'hxc_qd', qd)
    sd = good('sdu', 'sdu', sdu)
    ori = good('oric-mfm-side-major', 'oric_dsk', oric)
    good('oric-mfm-cylinder-major', 'oric_dsk', oric, geometry=2)
    good('oric-sector', 'oric_dsk', oric, raw=False)
    hs = good('pauline-nonzero-authenticated-padding', 'hxc_stream', stream)
    good('pauline-zero-padding', 'hxc_stream', stream, nonzero_padding=False, packets=1)
    good('pauline-empty-flux', 'hxc_stream', stream, empty=True, packets=1)
    af = good('afi-zlib', 'hxc_afi', afi)
    good('afi-stored', 'hxc_afi', afi, compressed=False)
    good('afi-reserved-packer-preserved', 'hxc_afi', afi, reserved=True)
    good('afi-string', 'hxc_afi', afi, strings=True)
    sv = good('svd-v20', 'svd', svd)
    good('svd-v12', 'svd', svd, version='1.2')
    good('svd-v15', 'svd', svd, version='1.5')
    good('svd-gcr-preserved', 'svd', svd, type_=16)
    good('svd-rnib-preserved', 'svd', svd, type_=64)
    fe = good('fei-dd-crc-identity', 'fei', fei)
    good('fei-hd-crc-identity', 'fei', fei, track_bytes=25000)
    ar = good('a2r-solved-only', 'apple_a2r', a2r)
    good('a2r-solved-v1', 'apple_a2r', a2r, version=1)
    good('a2r-solved-empty-unformatted', 'apple_a2r', a2r, empty=True)
    good('a2r-solved-with-raw', 'apple_a2r', a2r, mixed=True)
    good('a2r-multi-track-over-old-work-budget', 'apple_a2r', a2r, large=True)
    for name, reader, data, expected in list(cases):
        if name=='dim-sparse-preserved':
            # Sparse framing is unknown: shortening its opaque body is not a
            # proved truncation. Test its known envelope bounds separately.
            continue
        # A new empty solved chunk ends with a mandatory marker too.
        bad(name+'-truncated', reader, data[:-1])
    bad('ext-adf-bitlength-oob', 'amiga_ext_adf', altered(adf, 20, 0xff))
    bad('ext-adf-odd-track-allocation', 'amiga_ext_adf', altered(adf, 19, 1))
    bad('old-ext-adf-sector-size', 'amiga_old_ext_adf', altered(old, 15, 1))
    bad('dim-bad-side', 'atari_dim', altered(di, 6, 2))
    bad('stw-wrong-track-identity', 'atari_stw', altered(sw, 14, 1))
    bad('stt-section-backward', 'atari_stt', altered(st, 32, 1))
    bad('dfi-block-length-overflow', 'discferret_dfi', altered(df, 10, 0xff))
    bad('qd-overlap', 'hxc_qd', altered(qu, 529, 4))
    bad('sdu-size-mismatch', 'sdu', altered(sd, 45, 3))
    bad('oric-unknown-geometry', 'oric_dsk', altered(ori, 16, 9))
    bad('pauline-crc-damage', 'hxc_stream', altered(hs, 31, hs[31]^1))
    bad('afi-header-crc-damage', 'hxc_afi', altered(af, 31, af[31]^1))
    bad('afi-data-crc-damage', 'hxc_afi', altered(af, 122, af[122]^1))
    bad('afi-authenticated-bad-adler', 'hxc_afi', afi_authenticated_mutation(af, adler=True))
    bad('afi-authenticated-size-mismatch', 'hxc_afi', afi_authenticated_mutation(af, wrong_size=True))
    bad('pauline-authenticated-pulse-count', 'hxc_stream', stream_authenticated_mutation(hs, pulses=True))
    bad('pauline-authenticated-size-mismatch', 'hxc_stream', stream_authenticated_mutation(hs, wrong_size=True))
    bad('pauline-authenticated-invalid-lz4', 'hxc_stream', stream_authenticated_mutation(hs, lz4=True))
    bad('pauline-authenticated-duplicate-packet', 'hxc_stream', stream_authenticated_mutation(hs, duplicate=True))
    bad('svd-unknown-encoding', 'svd', altered(sv, len(b'2.0\n2\n2\n2\n1\n0\n'), 3))
    bad('fei-length-only-no-mfm', 'fei', bytes(len(fe)))
    bad('fei-wrong-id-crc', 'fei', altered(fe, 19, fe[19]^0x80))
    # Duplicate solved locations across entries must not silently replace data.
    bad('a2r-duplicate-solved-location', 'apple_a2r', altered(ar, 106, 0))
    bad('a2r-mirror-underflow', 'apple_a2r', altered(ar, 80, 1))
    bad('a2r-unknown-solved-version', 'apple_a2r', altered(ar, 61, 3))
    sparse, _ = dim(sparse=True)
    bad('dim-sparse-known-upper-bound', 'atari_dim', sparse[:32]+pattern(4097))
    with tempfile.TemporaryDirectory(prefix='xfu-hxc-tracks-') as temporary:
        folder = Path(temporary)
        lifecycle_readers = set()
        for case in cases:
            reader, expected = case[1], case[3]
            check_lifecycle = lifecycle if expected is not None and reader!='apple_a2r' and reader not in lifecycle_readers else None
            run_case(executable, probe, folder, *case, lifecycle=check_lifecycle)
            if check_lifecycle: lifecycle_readers.add(reader)
    print(f'{len(cases)} independent container cases passed.')


if __name__=='__main__': main()
