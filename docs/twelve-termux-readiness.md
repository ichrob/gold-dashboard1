# Manual Termux research preparation

No vendor requests, automatic workers, shared-quota claims or production changes
are authorized by installing dependencies or passing these checks.

In a separate private checkout, install `requirements-twelve-research.txt`.
Termux additionally requires `libpq`, the client library without a database
server. IANA `tzdata` is required when the Python environment lacks system
timezone files. Never replace Australia/Sydney with a fixed UTC offset: daily
bars cross summer/winter time.

Offline validation:

```sh
python -m unittest test_twelve_research_storage_bridge test_twelve_research_extension test_gold_fallback test_twelve_research_cli_cleanup
python twelve_research_extension.py --symbol XAU/USD --interval 1h --preflight
```

15 November 2026 Android/Python 3.14 observations: missing timezone database and
PostgreSQL client prevented the initial tests. After tzdata, psycopg and libpq
installation, the original 30 tests passed. A separate synthetic local probe
made twelve concurrent reservations: seven accepted, five refused; a new
process remained refused, and seven reservations persisted in the same ledger.
A synthetic AES-GCM file was reopened, authenticated and removed successfully
with private 0600 permissions. These are local tests, not provider credit,
Google Drive, backup erasure or account-wide exclusivity evidence.

Before a real request, the owner must identify other applications/devices using
the same provider account; a locally correct ledger cannot see their requests.
Use only an existing protected runtime's secret-input path for the key. There
is no approved secret-entry UI in this preparation, and no key should be put in
chat, shell command arguments, screenshots or the repository. The existing
encrypted backup vault must not be repurposed to extract credentials.

Remaining gates: protected key provisioning, exclusive account-wide credit
accounting, Bob's own OAuth access to the private archive, and verified erasure
of licensed originals including external copies after access termination.
Follow TWELVE_DATA_STORAGE_HANDOFF.md. Do not mark these gates passed just
because the owner authorized preparation or the offline tests succeed.
