# Current forward outcomes before historical catch-up

The existing audit worker runs about every two minutes and rotates six
horizons. A newly mature 60-minute case could therefore wait around twelve
minutes for its next scheduled horizon, even when its original follow-up
quote was already stored. This is a reproduced scheduling delay, not proof
that all historical missing outcomes share that cause.

Every normal harvest now attempts a 16-case recent 60-minute lane before
another horizon. Its remaining recent lane is reduced from 128 to 112
candidates, retaining the 128-case total recent budget. When 60 minutes is
already selected, its single lane retains the full 128-case budget. The
existing 64-case historical lane, durable rotation and timeout fallback
continue independently. A failed priority query rolls back its savepoint;
later horizons and archive work still run. No new worker or data table is
added; the existing primary key prevents duplicate outcomes.

Only existing original quotes from the approved stream in the unchanged
one-minute forward tolerance may produce an outcome. Missing, foreign or
out-of-window evidence remains unknown. Original start clocks, frozen
payloads, historical results and trading rules are unchanged. Database and
provider failures can still defer an attempt; the cadence is no latency SLA.

Validation includes first-pass PostgreSQL recovery while another horizon is
selected, source/clock rejection, idempotence, immutable input and the bounded
row budget. Functional success in ordinary trading still needs observed
post-release cases.

Related work was checked before adding another implementation: recent device
observations already confirm the previously missing LV field for its exact
target; remaining quote/time gaps are separate. Data-freshness instrumentation
is already present. Existing verified cold-storage offloads continue under
their current pressure cadence; logical payload reduction is not physical
disk reclamation, and weekend/restore/reserve gates remain required.
