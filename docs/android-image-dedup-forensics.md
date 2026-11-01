# Private Android / DEGIRO screenshot deduplication feasibility check

This change implements **only the initial evidence-gathering phase** of a
lossless screenshot storage optimization. It does not store image bodies
outside their current PostgreSQL JSONB row, alter batch readers, or modify
the existing 24-hour retention of temporary screenshot batches.

## Existing safety guarantees

- `android_list.validate` already rejects identical PNG SHA-256 values
  **within the same uploaded batch** (1–4 images); it has no cross-batch
  check. Different batches must remain independently readable and must not
  be turned into duplicates solely because they cover a similar product.
- The existing `bob_android_list_images` table holds complete base64 PNG
  strings under `payload.images[].png`; the importer expires entries only
  under its existing 24-hour lifecycle. The metadata, device and batch
  identity are not part of this analysis.
- A no-delete tail-VACUUM on 1 Nov 2026 reduced allocated relation bytes
  by only **24,576 B** without an independently proved physical Render
  volume decline; repeating that maintenance is not a substitute for
  reducing future stored bytes.

## New diagnostic: `androidImageDuplication`

A read-only aggregate, accessible only through the existing authenticated
storage report, checks **at most eight newest, still-unexpired image batches**.
It works entirely inside PostgreSQL with a 1.5s statement timeout,
500ms lock timeout and a 15-minute in-process cache. The SQL handles at
most 4 images per batch under the existing 2,000,000 encoded-character
validation, and returns **only five integer aggregates**: sampled batches,
sampled images, total encoded PNG characters, fingerprint-matched image
candidates and candidate repeated encoded characters.

Candidate equality uses a server-side MD5 of base64 **text** plus the
encoded character count. Hashes, batch IDs, screenshot bytes, account
details, app text and ISINs never leave PostgreSQL as output. A matching
MD5 fingerprint is **not** cryptographic proof of exact PNG equality;
reports explicitly mark `exactDuplicateProven=false`.
`candidateRepeatedEncodedCharacters` must **never** be called bytes freed,
TOAST bloat, a physical-volume reduction, or guaranteed deduplication
savings. This is a small recent-cohort sample, not all image history;
`additionalBatchesMayExist` is true when the eight-batch cap is reached.

If the table or required permission is absent, the query times out, or
the DB returns invalid types, the diagnostic shows `not-observed`;
missing data cannot be represented as zero duplicates. No new SQL
extension, write, index, scheduler or privileged remote connection.

## Decision before changing storage

Only if the bounded sample finds repeated candidates should a separate
change implement a **cryptographic, byte-for-byte validated** equality and
content-addressed storage. That future design must preserve every
original batch's metadata, original image timestamp, 24h access rights
and external DEGIRO read-through format, forbid cross-user access, verify
identical PNG bytes on upload and retrieval, be transactionally
recoverable and have an independently restored backup of both object and
reference ledgers. A checksum alone cannot authorize replacing original
bytes, and an archive pointer must never be promoted to a fresh quote.

Before considering any physical database rewrite, independently measure
free Render volume, WAL/scratch/locking budget, restore ability, and
absence of lost readers. No blind `VACUUM FULL`, source deletion, shorter
retention, account exposure, new paid services or trading actions.

## Production baseline, 1 November 2026

At roughly 13:08 UTC the authenticated Bob report showed about
**677.27 MB** physical PostgreSQL volume use, around **567.20 MB**
logical database size, and `bob_android_list_images` at
**11,411,456 B** allocated. Recent two-hour relation growth remained
dominated by image imports. These are independent measurements; they
are **not** proof of recoverable physical capacity.


## Exact in-memory proof (second, separately bounded pass)

When the aggregate candidate sample contains at least one repeated fingerprint,
the private diagnostic can perform a **second read-only pass on the same
maximum-eight-batch cohort**. This is permitted only when the first pass
contains at most 12 million encoded characters. The second pass retrieves
only PNG base64 strings into the existing trusted Bob server memory for
transient verification. It neither logs nor returns those strings.

Bob decodes each original PNG, checks the PNG magic, calculates SHA-256
over the actual PNG bytes, and verifies **full byte-for-byte equality**
against any same-hash earlier PNG before counting it as an exact repeated
image. To reject a different batch arriving between the two queries,
the second pass recomputes all first-pass MD5+length aggregate counters
and the total encoded length and compares them with the first observation.
Any mismatch is `cohort-changed`, never a successful proof.
Insufficient rights, malformed PNG, timeout or exceedance of the cap
returns an explicit incomplete status, not zero duplicates.

The report can then include
`exactVerificationStatus=verified`,
`exactDuplicateImages`,
`exactRepeatedEncodedCharacters`,
`exactRepeatedPngBytes` and
`exactDuplicateProven=true` if actual identical bytes are observed.
These are **potential future storage optimization quantities only**.
They do not mean those bytes are reclaimable from PostgreSQL, that
references are safe, that backup chunks exist, or that Render physical
volume decreased. A later content-addressed implementation would
require its own new PR, safe compatibility and restore tests, a small
explicit opt-in pilot, original batch identifiers and screenshot clocks
retained, and a measured physical-volume benefit before expansion.
