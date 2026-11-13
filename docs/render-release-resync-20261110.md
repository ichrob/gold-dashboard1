# Render release resynchronization — 2026-11-10

## Verified state before retry
- Target: `ichrob/gold-dashboard1`, branch `main`.
- Intraday feature change: pull request #1532, merged as `8e50df5a8367d7634ad57bff6aa92387ba67c505`. Same tested code tree as successful PR CI.
- Render services `bob-private-scanner` and `bob-push-service` were still at live commit `1ee534ab373ece182663a4aa12a941962efbb810` more than one hour after merge.
- Both Render services use `autoDeploy=yes`, `autoDeployTrigger=checksPass` and branch `main`. Render had no deployment event for the intraday merge.
- GitHub CI workflow `.github/workflows/ci.yml` has a `push` trigger on `main` and a fail-closed `release-gate` job for main pushes; PR CI alone does not prove the main release gate succeeded.

## Recovery action
This documentation-only follow-up commit intentionally causes a new ordinary push event on `main`, so that the existing `Bob CI` and `Bob release gate` can run and Render can release automatically after successful checks. This is *not* an untested code change or a manual Render bypass.

## Required release evidence
1. The GitHub `main` commit and its `Bob CI` run complete with `Bob release gate` success.
2. Render builds and deployments for **both** scanner and push service reach `live` on the new commit.
3. Read-only Bob diagnoses show fresh background and analysis clocks, 84 intraday study arms (14 variants × three durations × original/modeled), and no regression in KO/stop/source freshness.
4. Only then close tracking issue #1533. Do not treat a successful PR job, GitHub file update, or absent Render failure as live deployment evidence.

No real orders are enabled. Preserve the 30–300-minute intraday research scope and the original past results.
