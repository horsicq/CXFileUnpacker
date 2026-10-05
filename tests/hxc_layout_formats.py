#!/usr/bin/env python3
"""Independent raw mapping and XML initialized-sector byte checks."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

def pattern(size):
    block = bytes((i * 7) & 255 for i in range(256))
    return b"".join(bytes((v + c) & 255 for v in block) for c in range((size + 255) // 256))[:size]

def xml(body, name="Independent layout", geometry="<number_of_track>1</number_of_track><number_of_side>1</number_of_side><sector_per_track>2</sector_per_track><sector_size>128</sector_size><formatvalue>0xA6</formatvalue>", header=""):
    return (header + '<disk_layout><disk_layout_name>' + name + '</disk_layout_name><layout>' + geometry + body + '</layout></disk_layout>').encode()

def run(exe, args):
    p = subprocess.run([str(exe), *map(str, args)], capture_output=True, timeout=30)
    return p, (p.stdout + p.stderr).decode("utf-8", errors="replace")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacker", type=Path, required=True)
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--facts", type=Path)
    args = parser.parse_args()
    exe = args.unpacker.resolve()
    checks = 0
    p, message = run(exe, ["--raw-profiles"])
    assert p.returncode == 0 and len(message.splitlines()) == 102 and "hxc-raw:DOS_EXHD_6M78" in message, message
    p, message = run(exe, ["--raw-profiles", "unexpected"])
    assert p.returncode == 2, message
    checks += 2
    with tempfile.TemporaryDirectory(prefix="xfu-hxc-layout-") as tmp:
        folder = Path(tmp)
        def unpack(label, data, expected, reader=None, valid=True):
            nonlocal checks
            source, output = folder / (label + ".bin"), folder / (label + "-out")
            source.write_bytes(data)
            before = hashlib.sha256(data).digest()
            options = ["--reader", reader] if reader else []
            p, message = run(exe, ["x", source, "-o" + str(output), *options])
            files = sorted(p for p in output.rglob("*") if p.is_file()) if output.exists() else []
            if valid:
                assert p.returncode == 0, (label, p.returncode, message)
                assert [p.read_bytes() for p in files] == [data, expected], (label, message, [(p.name, p.stat().st_size) for p in files], len(expected))
            else:
                assert p.returncode != 0 and not files, (label, p.returncode, message, files)
            assert hashlib.sha256(source.read_bytes()).digest() == before, label
            checks += 1
            return source

        # Independent documented uniform and mixed-sector raw shapes. A raw
        # profile is explicitly selected and the entire original is retained.
        for name, size in (("DOS_DD_720KB", 737280), ("ENSONIQ_EDM", 80 * 5632),
                           ("OBERHEIM_DPX", 80 * 2 * 5632), ("X68000_HDM", 77 * 2 * 8192)):
            data = pattern(size)
            unpack(name, data, data, "hxc-raw:" + name)
        # The explicit Heathkit canonical CHS profile keeps source order;
        # ambiguous historical side orders can be supplied through the API.
        data = pattern(40 * 2 * 10 * 256)
        unpack("heathkit-order", data, data, "hxc-raw:HEATHKIT_40T_DS")
        data = pattern(80 * 2 * 2560)
        expected = b"".join(data[(h * 80 + c) * 2560:(h * 80 + c + 1) * 2560] for c in range(80) for h in range(2))
        unpack("arburg-side-major", data, expected, "hxc-raw:ARBURG_DATA")
        # The ADFS160 layout declares two heads but explicitly leaves side1
        # unformatted. It has no side1 sectors to initialize or recover.
        data = pattern(40 * 16 * 256)
        source = unpack("adfs-unformatted-head", data, data, "hxc-raw:ACORN_ADFS_160K")
        p, message = run(exe, ["l", source, "--reader=hxc-raw:ACORN_ADFS_160K", "--advanced"])
        assert p.returncode == 0 and "mapped sector bytes" in message and "40 cylinders, 2 heads" in message, message
        checks += 1

        # This84-cylinder preset declares80 source cylinders; the final four
        # cylinders contain declared0xE5 initialization rather than input.
        data = pattern(80 * 2 * 9 * 512)
        source = unpack("atari-generated-tracks", data, data + bytes([0xE5]) * (4 * 2 * 9 * 512), "hxc-raw:ATARIST_DD_720KB")
        p, message = run(exe, ["l", source, "--reader", "hxc-raw:ATARIST_DD_720KB", "--advanced"])
        assert p.returncode == 0 and "generated, not recovered" in message, message
        checks += 1

        # XML interprets logical sector data and declared fill, preserving the
        # complete descriptor separately. Neither it nor the raw parser opens
        # external paths referenced by XML.
        uniform = xml("", header='<?xml version="1.0"?>\n<!--primary descriptor grammar-->\n')
        unpack("xml-uniform", uniform, bytes([0xA6]) * 256)
        mixed = xml('<track_list><track track_number="0" side_number="0"><data_offset>0x40</data_offset>'
            '<sector_list><sector sector_id="2" sector_size="4"><data_fill>0x7B</data_fill></sector>'
            '<sector sector_id="1" sector_size="8"><sector_data><![CDATA[01 02 03 04 05 06 07 08]]></sector_data></sector>'
            '</sector_list></track></track_list>')
        unpack("xml-inline-sorted", mixed, bytes(range(1, 9)) + bytes([0x7B]) * 4)
        partial = xml('<track_list><track track_number="0" side_number="0"><sector_list>'
            '<sector sector_id="1" sector_size="8"><sector_data>deadBEEF</sector_data></sector>'
            '</sector_list></track></track_list>')
        unpack("xml-inline-zero-tail", partial, bytes.fromhex("deadbeef") + bytes(4))
        no_external = xml('<raw_file>must-not-open-secret.bin</raw_file>')
        (folder / "must-not-open-secret.bin").write_bytes(b"private source bytes")
        unpack("xml-external-reference", no_external, bytes([0xA6]) * 256)
        side_geometry = '<number_of_track>2</number_of_track><number_of_side>2</number_of_side><sector_per_track>1</sector_per_track><sector_size>4</sector_size><formatvalue>3</formatvalue>'
        side = xml('<track_list><track track_number="1" side_number="0"><sector_list>'
            '<sector sector_id="1" sector_size="2"><data_fill>9</data_fill></sector></sector_list></track></track_list>', geometry=side_geometry)
        unpack("xml-track-override", side, bytes([3]) * 8 + bytes([9]) * 2 + bytes([3]) * 4)
        trailer = xml('<track_list><track track_number="1" side_number="0"><sector_list>'
            '<sector sector_id="1" sector_size="4"><sector_data>cafebabe</sector_data></sector>'
            '</sector_list></track></track_list>')
        source = unpack("xml-bounded-outside-trailer", trailer, bytes([0xA6]) * 256)
        p, message = run(exe, ["l", source, "--advanced"])
        assert p.returncode == 0 and "1 track declaration(s) ignored outside declared geometry" in message, message
        checks += 1

        bad = [
            ("xml-wrong-root", b"<manifest><layout/></manifest>"),
            ("xml-unclosed", uniform[:-2]),
            ("xml-dtd", b'<!DOCTYPE disk_layout SYSTEM "must-not-open-secret.bin">' + uniform),
            ("xml-two-roots", uniform + uniform),
            ("xml-overflow", uniform.replace(b"<number_of_track>1", b"<number_of_track>999999999999999999999999")),
            ("xml-negative", uniform.replace(b"<sector_size>128", b"<sector_size>-1")),
            ("xml-duplicate-dim", uniform.replace(b"<layout>", b"<layout><number_of_track>1</number_of_track>")),
            ("xml-scalar-child", uniform.replace(b"<sector_size>128", b"<sector_size><ignored/>128")),
            ("xml-root-tracklist", uniform.replace(b"</disk_layout>", b'<track_list><track track_number="0" side_number="0"/></track_list></disk_layout>')),
            ("xml-bad-hex", mixed.replace(b"01 02 03", b"01 Z2 03")),
            ("xml-long-inline", partial.replace(b"deadBEEF", b"AA" * 9)),
            ("xml-duplicate-sector", mixed.replace(b'sector_id="2"', b'sector_id="1"')),
            ("xml-outside-hard-bound", mixed.replace(b'track_number="0"', b'track_number="256"')),
            ("xml-ignored-track-bad-inline", trailer.replace(b'cafebabe', b'cafebabeff')),
            ("xml-ignored-track-missing-id", trailer.replace(b'sector_id="1"', b'')),
            ("xml-ignored-track-duplicate-id", mixed.replace(b'track_number="0"', b'track_number="1"').replace(b'sector_id="2"', b'sector_id="1"')),
        ]
        for label, data in bad:
            unpack(label, data, b"", "hxc_xml_disk_layout", False)
        raw = pattern(737280)
        for label, data, name in (("short-raw", raw[:-1], "DOS_DD_720KB"),
                                  ("long-raw", raw + b"X", "DOS_DD_720KB"),
                                  ("unknown-profile", raw, "UNKNOWN_PROFILE")):
            unpack(label, data, b"", "hxc-raw:" + name, False)
        source = folder / "explicit-syntax.bin"
        source.write_bytes(raw)
        for options in (("--reader",), ("--reader=",), ("--reader", "bad-name"),
                        ("--reader", "hxc-raw:DOS_DD_720KB", "--reader", "hxc-raw:DOS_DD_720KB")):
            p, message = run(exe, ["t", source, *options])
            assert p.returncode == 2, (options, message)
            checks += 1
        # Optional primary-source integration verifies every unmodified XML
        # preset independently against the pinned factual sector inventory.
        if args.upstream and args.facts:
            import json
            facts = json.loads(args.facts.read_text())
            for profile in facts["profiles"]:
                if not profile["provenance"]["path"].endswith(".xml"):
                    continue
                data = (args.upstream / profile["provenance"]["path"]).read_bytes()
                expected = b""
                for sector in sorted(profile["sectors"], key=lambda s: (s["c"], s["h"], s["id"])):
                    inline = bytes.fromhex(sector.get("inline_hex", ""))
                    expected += inline.ljust(sector["size"], b"\0") if inline else bytes([sector["fill"]]) * sector["size"]
                unpack("primary-" + profile["name"], data, expected, "hxc_xml_disk_layout")
    print(f"HxC raw/XML layouts: {checks} extraction, metadata and malformed-input checks passed")

if __name__ == "__main__":
    main()
