# BALZ And BCM Reader Provenance

The xxfclib-only build retains BALZ and BCM reading through the local xxfclib
source tree. XFileUnpacker does not compile its former application-side BALZ or
BCM encoders, so `xfu --capabilities` reports `create=no` for both formats.
Creation requests fail explicitly instead of invoking another program or
silently selecting another format.

BALZ 1.20 was placed in the public domain by its author. The original source
archive is available from the
[author's SourceForge release](https://sourceforge.net/projects/balz/files/BALZ/1.20/).
BCM is Copyright (C) 2008-2021 Ilya Muravyov, is licensed under Apache-2.0,
and is available from the [BCM source mirror](https://github.com/FS-make-simple/bcm).

The former application-side writer adaptations, vendored helper codecs and
development-only upstream comparison tools have been removed from this source
tree. No libsais package is downloaded, discovered or linked by
XFileUnpacker.
