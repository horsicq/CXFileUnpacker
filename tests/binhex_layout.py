"""Verify BinHex framing, decoded contents and CRC rejection through the CLI."""
import binascii
import pathlib
import struct
import subprocess
import sys
import tempfile

ALPHABET = b'!"#$%&\'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr'
BANNER = b"(This file must be converted with BinHex 4.0)"


def crc(data):
    return struct.pack(">H", binascii.crc_hqx(data, 0))


def encode(data):
    rle = data.replace(b"\x90", b"\x90\x00")
    bits = count = 0
    result = bytearray()
    for value in rle:
        bits = (bits << 8) | value
        count += 8
        while count >= 6:
            count -= 6
            result.append(ALPHABET[(bits >> count) & 63])
    if count:
        result.append(ALPHABET[(bits << (6 - count)) & 63])
    return bytes(result)


def main():
    unpacker = pathlib.Path(sys.argv[1]).resolve()
    name = b"example"
    data, resource = b"BinHex data \x90 with a literal escape\n", b"resource fork\n"
    header = (bytes([len(name)]) + name + b"\0TEXTttxt" +
              struct.pack(">HII", 0, len(data), len(resource)))
    decoded = header + crc(header) + data + crc(data) + resource + crc(resource)
    with tempfile.TemporaryDirectory(prefix="xfu-binhex-") as temporary:
        root = pathlib.Path(temporary)
        for index, separator in enumerate((b"", b"\r\n\r\n", b" \t\n")):
            source, output = root / f"valid{index}.hqx", root / f"out{index}"
            source.write_bytes(BANNER + separator + b":" + encode(decoded) + b":")
            result = subprocess.run([str(unpacker), "x", str(source), "-o" + str(output)],
                                    capture_output=True, timeout=15)
            assert result.returncode == 0, result.stdout + result.stderr
            assert (output / "example").read_bytes() == data
            assert (output / "example.rsrc").read_bytes() == resource
        for index, bad in enumerate((decoded[:len(header)] + b"\0\0" + decoded[len(header)+2:],
                                     decoded[:-1] + bytes([decoded[-1] ^ 1]))):
            source, output = root / f"bad{index}.hqx", root / f"badout{index}"
            source.write_bytes(BANNER + b":" + encode(bad) + b":")
            result = subprocess.run([str(unpacker), "x", str(source), "-o" + str(output)],
                                    capture_output=True, timeout=15)
            assert result.returncode != 0
            assert not any(output.rglob("*")) if output.exists() else True
    print("BinHex adjacent/multiline banner layouts and invalid CRCs passed")


if __name__ == "__main__":
    main()
