# Decision-audit storage: read-only field footprint and archive gates

## Confirmed production state (31 Oct 2026, 14:48 UTC)

The private storage catalog measured `bob_decision_audit` at **139,796,480 allocated bytes**:
9,371,648 heap, 7,577,600 indexes, 122,814,464 TOAST and 32,768 other.
The catalog's estimated row count was 276; estimates are not exact counts and
relation allocation is not a measurement of reclaimable space. The independent
Render-volume meter was at 689,557,500 bytes. No data was removed here.

## Why direct JSON-pointer replacement is unsafe

The original `bob_decision_audit.payload` is used by *SQL*, not only Python.
Any generic replacement with a Drive reference would silently change:

- The `bob_audit_evaluable_cursor` and prospective indexes whose predicates
  inspect `marketEvaluable`, `recordedAt`, `reviewVariants`, `origin`,
  `direction` and `ruleVersion`.
- The recent and seven-day outcome harvest, which tests `marketOptimization`
  and `entryQuality` and derives original recorded time from JSON.
- The 30-day prospective query and its bounded 24-hour fallback.
- Day-history summaries, first qualifying signals, full page reads and
  comparative reviews in `audit_history` and `decision_audit`.
- Exact record and evidence consumers in other subsystems that must be
  enumerated before a write-side change.

The private reader `bob_diagnostics.stored_details` also performs a bounded full-payload SQL read of the newest 20 decisions; it must stay compatible with any cold references. `stop_target_audit` maintains a foreign-key reference to decision IDs, so those IDs must remain in PostgreSQL.

Historical decisions may be used to compare simulation and product selection.
Do not modify original timings, numeric values, eligibility, directions, or
gates as part of storage optimization.

## New diagnostic

`storage.layout.decisionPayloadSample` is read-only and explores at most
four oldest and four newest immutable audit rows, deduplicating their IDs.
It aggregates nested JSONB sizes into a fixed list of field groups and
`other-fields`. It returns *no* raw evidence, source URL, original JSON key
outside the fixed allowlist, ISIN, price, credential or payload. It returns
`not-observed` if the table is absent or the query fails. This is not an
exact survey or direct physical TOAST storage measurement.

Because the private MCP projection can omit newly added optional report fields,
`BOB_DECISION_FOOTPRINT` emits **one** size-only sanitized summary per process
to private Render app logs after a successful sample, never raw evidence. Only
the fixed field-group allowlist, bounded counts and aggregated sizes are logged;
unrecognized keys or invalid sizes abort logging. This does not send Push,
email or market data, and never authorizes archival or compaction.

PostgreSQL integration regressions assert an eight-record bound, the absence
of original values in the result, read-only behavior, missing-table isolation,
and empty-table handling.

## Preconditions for a future lossless offload

1. Map every SQL predicate and reader of the original payload across the entire
   repo, including adjacent tests and background workers. Do not assume the
   audit history reader is the only consumer.
2. Choose a field-level split only after sample sizes identify the large
   children; retain SQL-dependent fields *inline* unchanged.
3. Keep original row identity, clocks, outcomes, and numeric JSON serialization.
   Upload encrypted/private immutable Drive chunks, verify SHA-256 by remote
   download, compare original reads, and commit atomic compare-and-swap pointers.
4. Maintain exact read-through for each report, replay and historical lookup;
   raise an explicit incomplete result on missing/corrupt remote chunks.
   Roll out compatible readers on **both** services before enabling any writer.
5. Compare PostgreSQL TOAST, heap, indexes, full logical DB and independent
   Render volume after a documented safe maintenance window. Offload and
   deleted TOAST chains do not automatically produce volume free space.
6. Require PostgreSQL integration, original-row equality, numeric precision,
   indexed predicate consistency, concurrent replay and rollback tests,
   restored-backup proof and error-path tests. Preserve app availability:
   earlier index maintenance caused transient database lock and timeout errors.

There is **no audit archive writer or automatic compaction enabled** by this
measurement-only change. It performs no orders, data deletion, paid scaling or
retention shortening.


## Age-cohort sample before product-field migration

The first eight-row production observation on 31 October measured
26,398 serialized nested JSONB bytes for products out of approximately
44,700 bytes of sampled child fields (about 59%). It is *not* proof that
products occupy 59% of the table or that removing products will return
physical disk capacity. The entire decision audit still includes a
122.8 MB TOAST relation whose live/dead page composition is not known.

`storage.layout.decisionProductsCohorts` reads at most eight IDs per indexed
window: oldest, newest, most recent before 24 hours, before seven days,
before 14 days, and before 30 days. Windows can overlap. Only aggregate JSON text
bytes, counts of populated product arrays, distinct arrays within each
window, and the unique sampled row count are returned. Neither original
products nor hashes/IDs/timestamps are exported. This is a biased diagnostic
sample of at most 48 selections, not a random or full archive survey.
A failed/missing-table query returns `not-observed`, without corrupting
the containing storage report or making write-side changes.

`products` is visible directly in `audit_history.compact` and
`decision_audit.product_review` (including quotes, selection and original
reasons), while the private diagnostics and aggregate research reports
consume the full decision JSON. An optimization must not replace product
values with an opaque pointer until each affected consumer uses a verified,
exact read-through, with immutable row identity, original sequence,
precision and timestamps. A seemingly repeated array is not permission
to deduplicate without full original comparison and identity isolation.

This change **does not** enable any product offload, backlog deletion,
automatic FULL/VACUUM, trade mutation or paid scaling. Compare independent
physical-volume measurements only *after* a separate fully verified,
operator-budgeted maintenance step.

A separate bounded heap-only SELECT counts at most **10,001** row entries without
reading stored JSON/TOAST. If it reaches the cap the count is explicitly a
**lower bound**, not a population total. Counting can be unavailable
independently of the age-cohort profile. In particular, this can identify
stale `pg_stat` row estimates without a costly unbounded JSON scan.
Even a precise row count would not establish how much TOAST is reusable.

## Compatible read-through foundation (writer still disabled)

The optional `cold_decision_products.resolve(conn, decision_id, payload)`
returns every inline original unchanged, with no network or ledger lookup.
For any future `_bobColdDecisionProductsV1` pointer it requires a stored
content hash matching the exact decision ID in a read-only reference ledger,
and a separate object ledger with the Drive file ID, immutable SHA-256, and
chunk index. The shared chunk is downloaded using the existing checksummed
bounded cold-metric reader and verified against the original JSON products
hash before deep-copying the array into the unchanged report shape.
Absent ledgers/chunks, mismatched decision identity, invalid checksums,
ambiguous inline-plus-pointer records and corrupted content must all raise
an explicit incomplete-report error. Never substitute [] or a reconstructed
price. Read paths touched: current audit report, historical dated pages,
first-signal history, prospective review and private bounded diagnostics.

The ledger table names are reserved as
`bob_cold_decision_product_refs(decision_id,content_hash)` and
`bob_cold_decision_product_objects(content_hash,file_id,sha256,row_index)`;
this foundation creates **neither** table, writes **no** pointers, and
performs **no** upload, retention or compaction. A future writer requires
separate SQL migrations plus a two-service reader-then-writer rollout;
it must preserve immutable original decision IDs, SQL-dependent inline
fields, exact product list sequence and all numeric/time values, with CAS
and verified restore after restart. Historical reports must fail explicitly
if the Drive archive is unavailable.

Before enabling a writer, enumerate any remaining direct SQL JSON readers
and record a before/after regression for query predicates, trading-independent
decision replay, product comparisons, private diagnostic scope, archive
corruption, and independent volume measurement. No authorization to enable
the writer is implied by compatible readers.
## Manual-only cold product writer (default OFF)

`cold_decision_product_writer.py` supplies an *unregistered* manual writer.
It is not imported by push/scanner startup, background loops, or public routes.
`BOB_COLD_DECISION_PRODUCTS_ENABLED` defaults to absent/OFF. Even with the
flag enabled, `run_once` requires an explicit in-memory approval with fresh
`observedAt` (<=15 minutes), confirmed restore and confirmed remote download.
The caller, not the module, is responsible for obtaining independently
verified backup proof; no browser or external user action can authorize
writing by setting a flag in an HTTP request. This is **not** automatic rollout.

An explicit first-time `init` creates only the content-addressed object
ledger, per-decision reference ledger and durable scan cursor. It never
deletes audit source rows. An optional one-off batch scans at most twenty
ordered keys older than fourteen days, with a persistent cursor so sparse
product-bearing rows cannot cause repeated full JSONB scans. Empty or small
product lists are left inline. Selected nonempty lists are hashed using
the canonical JSON codec; identical hashes reuse a verified archived array.
New arrays are packed into a bounded gzip chunk (2 MiB raw, 500 entries),
uploaded to private Drive and re-downloaded with a verified complete SHA-256
before beginning any SQL update transaction.

The transaction inserts immutable object addresses, compare-and-swap updates
original decision rows by exact ID, timestamp and full original JSONB, and
inserts the decision-to-content-hash reference; the *same* exact read-through
adapter reconstructs and compares the preexisting decision before commit.
An unmatched concurrent update remains intact. An error rolls the whole
transaction back; remote unused uploads may remain and are **not** deleted
automatically. Previous and current SQL-indexed directional fields, clocks,
market conditions and outcomes remain inline. A failure to retrieve the
original archived list produces an explicit incomplete result, not `[]`.

The manual writer has no ability to release disk-space allocations by itself.
Archive JSON savings do not equal reduced TOAST pages, database size, or
Render physical volume. No REINDEX/VACUUM FULL is started. Never use this
writer in production before independently confirming all reader paths on
both services, database backups, Drive restore, live data counts, and a
maintenance budget with explicit approval. An enabled flag without proof
does not allow writes; only a deliberately invoked manual run with the
two-factor guards can proceed.

PostgreSQL integration tests use a locally simulated private Drive. They
verify one shared object for repeated arrays, exact original precision and
order, read-only archived readback, corrupt-download rollback, CAS under
concurrent modification and no-configuration no-op behavior. No real
product originals, account credentials or broker calls appear in fixtures.
## Live dry-run preflight and independent operational gates

An authenticated private storage report now exposes `decisionProductsPreview`,
which reads at most the 20 oldest decision IDs older than 14 days using the
existing recorded-time index. It reports only the number of eligible
product-bearing decisions, distinct array hashes as **counts**, reused-array
counts and logical before/after JSON sizes; it returns no ISIN, product price,
original record ID, SHA-256 string, credential or precise decision timestamp.
It never creates any ledger, uploads a file, calls a writer, or changes any row.
The preview is biased toward the oldest page, not a population estimate.

Most importantly, the private storage report attaches the **persisted**
backup receipt to the preview: `verified-fresh` requires an explicit verified
remote download and successful isolated restore, with the persisted receipt
no older than six hours. Earlier verification remains historically valid but
does not authorize current source updates. An unavailable or stale proof
causes the manual writer to exit **before** its table initialization.

Beyond the manual flag and caller-supplied approval, `run_once` independently
re-reads that persisted restore receipt and requires a live, under-five-minute
Render volume observation for the exact production Postgres resource with
usage <=750 MB (decimal). Missing telemetry or excessive disk usage blocks
writing. These are deliberately conservative short-term maintenance gates,
not permission to delete source data, claim free physical storage, or bypass
the verified Drive read-through. No public or automated writer invocation
is created by the preview.

The no-write rehearsal is intended to decide *whether* a first controlled
production archive batch makes sense. A separate explicit execution workflow
with proven rollback is still necessary before any pointer is committed.
## Interrupted full backup during rolling Render deploy (2026-10-31)

An explicit new full database export was successfully started at 18:54 UTC;
the process reached local restore, Drive upload/download and remote restore.
A separate Bob Handy code release deployed a new push-service process
at 19:02 UTC while remote restore was running. The original attempt
remains persisted as `running`, without a final restored receipt. This is
**not** a fresh verified backup and must not authorize archive source updates.
The successful earlier verified receipt remains factually valid at its
original date, but is **stale** for the six-hour writer gate.

`storage_budget.archive_status` now reports both the latest attempted run
and the latest successfully verified attempt, with sanitized identifiers.
A nonterminal claim older than ten minutes is a review candidate, not
proof that the old process failed. The new decision writer proof gate reads
the last independently verified restore timestamp, always applies its
six-hour freshness and still requires a separate short-lived manual approval
and Render disk observation. This is a read-only status correction.

The original database remains unchanged. Do not reset the incomplete
attempt row or pretend the uploaded but unverified Drive file is a
recoverable/verified source. Use a **new distinct attempt ID** for a
future full backup in a quiet deployment window, or implement separately
tested durable remote-restore resumption before the next pilot.
## Exactly-once single decision pilot (explicitly disabled unless approved)

An optional one-shot coordinator `decision_product_pilot.py` exists
**only as a manually invoked maintenance function**. It is not imported,
started or scheduled by either Render service. It still refuses invocation
unless BOTH `BOB_COLD_DECISION_PRODUCTS_ENABLED=1` and a strict operator
command `BOB_DECISION_PRODUCT_PILOT_ONCE={"id":"unique-operator-id",
"confirmed":true,"maxUpdates":1}` are supplied in a private maintenance
environment. Merely setting environment variables on a web service does
**not** initiate a migration. No HTTP route accepts this command.

An explicitly invoked single bounded run checks an independent recent
verified restore and exact resource-specific Render disk headroom,
then creates an immutable unique pilot ID claim in
`bob_cold_decision_pilot_attempts`. The ID can be inserted at most once,
including after a rolling deploy. A failed/interrupted attempt is never
automatically retried. The writer performs its own second backup, disk,
archive lock and caller-approval checks before any product changes.

The optional `max_updates=1` writer argument stops after the first eligible
historical decision in an indexed 20-row page, preserving the durable scan
cursor at that decision (never skipping the remaining eligible rows). It
may upload and replace exactly one old product array with a verified
content-addressed reference. On successful SQL commit it records the
read-through result in the pilot ledger. Failures retain their status
and exception *type* only, never a Drive file ID, ISIN or original value.

The private storage report exposes only the sanitized most recent pilot
state, row count and timestamp; it does not expose the command ID. If the
pilot is interrupted midflight the persistent `running` claim prevents
another implicit write, and human/operator examination of ledger and
archive proof is required before any distinct attempt.

No automated repeat schedule or broad writer enablement is provided.
After any manual pilot, the operator must clear the two opt-ins and verify
that all historic readers still resolve the exact original. The durable
historical attempt remains. A merge or Render deploy alone never runs it.
Logical JSON reduction **never** counts as physical Render volume savings.

## Explicit terminal maintenance command (does not run automatically)

The terminal-only module `decision_product_pilot_cli.py` is deliberately
not imported by push/scanner startup, background workers or web routes.
It accepts only three exact commands from a **private, authenticated
maintenance shell** with the existing application database and archive
credentials available to the process:

```sh
python -m decision_product_pilot_cli status
python -m decision_product_pilot_cli preflight
python -m decision_product_pilot_cli execute --acknowledge-one-row-only
```

`status` queries only the optional pilot claim receipt; `preflight`
independently checks backup and disk proof without any ledger creation,
writer invocation or upload. Preflight returning
`approved-for-single-row-pilot` means only that this *one read-only
probe* passed; it is **not** authorization to migrate. Only the exact
`execute` command can call `run_once`, and this additionally requires
the original strict `BOB_COLD_DECISION_PRODUCTS_ENABLED=1` opt-in and
`BOB_DECISION_PRODUCT_PILOT_ONCE` JSON with distinct claim ID,
`confirmed=true`, `maxUpdates=1`. These secrets and IDs must not be
pasted into a chat, a GitHub issue or command arguments.

The coordinator and writer then recheck the independent restore receipt,
the five-minute resource-specific Render disk proof, the durable one-use
claim and single-row CAS/read-through verification. A previous claimed
attempt is never silently retried. The command prints only an allowlisted
sanitized result (never an ISIN, claim ID, credentials, Drive file ID,
payload, SQL or exception message). It returns nonzero for any skipped,
failed or unverified write. No command frees allocated PostgreSQL volume
by itself. Do not execute during a deploy or a live full archive restore;
record before/after Render volume and PostgreSQL sizes independently.

The current connected Render management interface cannot execute a
remote shell command. Deployment, setting environment variables or merging
this command is **not** a substitute and must never launch a migration.


## Recovery completeness after the first product pointer (1 Nov 2026)

The existing reviewed-evidence backup already includes `bob_decision_audit`,
but before this safeguard it did **not** select the separately created cold
decision-product address and identity ledgers. Once a decision is represented
by `_bobColdDecisionProductsV1`, restoring the audit table without
`bob_cold_decision_product_objects` and
`bob_cold_decision_product_refs` would leave that historical product list
unresolvable even if its immutable Google Drive chunk still existed.

The selected evidence tables now also include those two ledgers, the
`bob_cold_decision_product_scan` cursor, and the
`bob_cold_decision_pilot_attempts` durable no-repeat receipt. They are
optional when a system has not performed its first manual product pilot:
an absent table must remain explicitly absent in the manifest, not turn
into invented data. OAuth, passkey, session and account-setting tables remain
outside the reviewed evidence scope. The private Drive archives must still
be retained and separately retrievable; exporting the DB ledger is **not**
itself a backup of the referenced Drive object.

A previously verified backup cannot retroactively gain tables added to the
export selection after it was made. After deployment of this safeguard,
an independently verified **new** export, download and restore must cover
any then-existing reference ledgers before further product pointers are
created. Verify the corresponding Drive chunks too. This remains a
reviewed-evidence backup, **not a full-database backup** or authorization
for automatic product archival, compaction, data deletion or paid scaling.


## One-use weekend tail-space reclaim after verified archival

`storage_tail_once.py` adds a **separate** opt-in to the existing
hourly storage-maintenance worker for `VACUUM`, not for product migration.
It is disabled by default. A one-time opt-in has the exact form
`BOB_STORAGE_TAIL_RECLAIM_ONCE={"id":"unique-maintenance-claim","table":"bob_diagnostic_history","confirmed":true}`.
Only `bob_diagnostic_history`, `bob_improvement_observations` and
`bob_metric_checks` are valid target names. No product, decision, order,
account, or original-archive table can be selected.

It refuses execution outside Saturday or Sunday before 20:00 in Zurich,
while a full archive run is active, without a persisted independent
verified download/restore receipt less than six hours old, or when
resource-specific Render disk telemetry is older than five minutes,
unknown, or above 750 decimal MB. The single-use ID is durably claimed
in `bob_storage_tail_reclaim_attempts` **before** the operation, so
a redeploy, timeout or restart never repeats the same attempt. The caller
may only select one allowlisted table per claim. The existing dedicated
connection/advisory lock, `VACUUM (SKIP_LOCKED, TRUNCATE TRUE, PARALLEL 0)`
and per-command 10-second statement timeout remain in force. It never
runs `VACUUM FULL`, `CLUSTER`, `REINDEX`, `DELETE` or source mutation.
Any blocked/failed/no-space run is labeled accordingly, not a success.

The operational receipt reports a size decrease in the **one table's
allocated relation bytes**, if observed; `diskBytesFreed` intentionally
remains null. It is not a claim of actual free Render disk bytes.
A separate, later independent Render volume measurement and original-row
read verification are needed to confirm physical savings. The maintenance
attempt log must not print command IDs, credentials or database originals.
Changing the configuration alone can trigger a regular Render redeploy;
do not enable it during an active archive restoration, unverified release,
or trading session. No new paid service or public database access is needed.


## Single guarded VACUUM for expired Android image-import tail pages

The existing Android list importer `android_list.py` already applies its
original 24-hour expiry to temporary `bob_android_list_images` entries.
A private PostgreSQL catalog observation on 1 Nov 2026 showed about 9 MB
allocated to this table, an estimated 7 live and 5 dead tuples. This is
a candidate for potential relation-end truncation, **not proof** that
its last pages are free or that physical Render volume would decrease.

The separately confirmed, default-OFF `BOB_STORAGE_TAIL_RECLAIM_ONCE`
single-table maintenance policy also permits `bob_android_list_images`
as a fixed target. It leaves the **existing 24-hour expiry unchanged**
and never adds a `DELETE`, overwrites saved screenshot values or modifies
its active product reader. The command is the same ten-second,
`SKIP_LOCKED`, `PARALLEL 0`, `TRUNCATE TRUE` regular `VACUUM` as the
prior approved one-row maintenance targets. Its independent restored
backup, fresh exact Render-volume observation, 750 MB ceiling, weekend
market closure, unique durable claim and fail-closed error policy are
unchanged. A new test proves exactly one invocation for that fixed
table; the existing code forbids arbitrary SQL identifiers.

Only an explicit separate one-time opt-in can trigger this after full
PR/Main CI, CodeQL, risk and actual Render deployment checks. After an
attempt, immediately clear the one-time setting and independently
compare both PostgreSQL relation bytes and Render physical DB volume.
Even a successfully completed VACUUM with 0 reduction is **not** a space
recovery. Do not lower image retention, remove original audit evidence,
rewrite the table or enable a public database connection to pursue it.
