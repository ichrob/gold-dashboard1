# Checked-commit fast-forward release recovery (2026-11-10)

## Incident
Bob intraday change #1532 was merged as 8e50df5a and an additional documentation-only push produced 0ba51ad5, but both Render services remained on 1ee534ab with autoDeployTrigger=checksPass. No Render deploy/build/ignored events were observed for either newer commit.

Render's documented checksPass behavior is fail-closed when a new commit has zero detectable checks or any failed check. The PR CI for #1532 was successful; it does not automatically transfer its check status to a new squash-merge SHA.

## Safe, bounded recovery
Create one new documentation-only commit on top of current main in a PR branch. Wait for **all** PR CI jobs for the precise head SHA to finish successfully. If successful, fast-forward the main branch to **the exact same tested SHA**, without a squash or merge commit, retaining the passing commit-associated checks so Render can evaluate it. Never force-push; require main to be the known ancestor and confirm it has not changed. Keep Render checksPass enabled.

This is a *single incident recovery*, not a change in automated trading, permission grants, release policies, or historical paper results. Test admission and current source/KO checks stay fail-closed. If no Render deployment occurs after the checked fast-forward, capture events and escalate without forcing a build.

## Success criteria
Both `bob-private-scanner` and `bob-push-service` show the exact same latest checked commit as `live` in Render. Read-only Bob diagnostics show the new 30–300 minute intraday study shape (14 variants × 3 horizons × two input streams = 84 arms) with current sources, while core paper accounts continue normally. Until those observations, issue #1533 remains open.
