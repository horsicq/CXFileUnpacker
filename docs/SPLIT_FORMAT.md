# Numbered Split Volumes

XFU can create and join raw numbered volumes in process, without the optional
7-Zip helper. This operation splits one file into consecutive byte ranges; it
does not compress data or add an archive header.

```text
xfu a output.001 input.bin --volume-size=10M
xfu a output input.bin --format=split --volume-size=64K
xfu l output.001 --reader split
xfu t output.001 --reader split
xfu x output.001 --reader split -ojoined
```

Creation accepts one regular file. A destination ending in `.001` names the
first part directly; otherwise `--format=split` appends `.001`. Parts are named
`.001` through `.999`, with a default maximum part size of 10 MiB. The CLI's
`K`, `M` and `G` suffixes mean binary multiples of 1,024. Empty input creates one
empty `.001` file; an exact multiple does not create an extra empty part.
Compression, encryption, outer filters and custom archive options are not
supported. Stored method aliases and compression level zero are accepted.

The reader starts only from `.001` and exposes one member named after the
series prefix's basename. For example, `backup.bin.001` extracts as
`backup.bin`. It requires contiguous regular-file siblings, equal-sized
nonfinal parts and a final part no larger than the first. Links, gaps,
inconsistent sizes and an unsupported `.1000` continuation are rejected.
An explicit `--reader split` selects this interpretation. The former
`sevenzip_split` helper reader is disabled; `--reader split` is the supported
in-process joining path. A series has no encryption, so
reading ignores a password (`-p`, or one left in the GUI field for another
archive).
The capability row is `native split read=partial create=yes`, reflecting the
series limits and missing integrity metadata rather than unrestricted support
for every application's multipart archive conventions.

Reading logs like the other readers: `<first>: Numbered split file`, the
member's line (its size and name when listing, `  name -- OK` when testing,
`  name` when extracting, or `  name -- FAILED`), then `1 member(s)` or
`1 member(s), 1 failed`. A Cancel while the member is read logs
`  name -- cancelled` and `0 member(s)`; a Cancel before it starts logs
`operation cancelled`. TEST's percentage reaches 100% only when the member was
read in full. Creation lists the input file, then
`<first>: 1 file(s) as split in N volume(s)`. Progress advances one volume at a
time.

## Limits And Safety

Raw split volumes contain neither checksums nor a recorded final volume count.
TEST verifies readability and the supported series structure; it cannot detect
changed bytes or a missing final part. Joining does not inspect or recursively
extract an archive that happens to be stored inside the parts.

Creation refuses an existing destination series, including late numbered parts.
Every part is written to an exclusive sibling staging file before publication.
Publication never overwrites an existing part. On error or cancellation, the
backend removes its staging files and rolls back newly published parts whose
file identity still matches its own output. Multiple filesystem renames are not
a single atomic transaction; process termination, filesystem failure or outside
interference can prevent complete rollback.

Extraction streams into one sibling staging file and replaces the destination
only after successful completion. Unsafe payload basenames, a link at the
payload's own path and output hard-link aliases of an input part are
rejected; the output folder and the folders above it may be links, as for
every other format. Selection
uses the single record index zero. TEST never creates an output file.

Data is processed in bounded 64 KiB chunks with cancellation/progress checks.
Source sizes, identities where available, and EOF are checked, but file contents
are not snapshotted. Concurrent same-size content modifications do not provide a
point-in-time consistency guarantee.

## Verification

```text
python tests/test_split_compat.py path/to/xfu
```

The focused suite checks byte-exact splitting and concatenation, empty and
Unicode inputs, volume-size parsing, aliases, malformed series, unsupported
options, existing-part preservation, unsafe names, links and TEST filesystem
invariance. Core C API checks additionally exercise callbacks, cancellation,
selection and publication rollback.
All 18 focused CLI tests passed in the Windows x64 MSVC Release build. Linux
and 32-bit application builds have not been run.
