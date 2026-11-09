# Bob: optional off-box OCR for memory pressure

## Zero-extra-charge provider decision

The owner requires a strict no-extra-charge design. No paid billing
activation or cloud resources may be created by this repository.

1. **Google Cloud Free Trial (short test only):** an eligible new customer
   receives a free-trial billing account with USD 300 / 90 days. Google
   says it does not bill usage during that trial unless the owner manually
   upgrades to a paid account. It stops workloads when the trial ends.
   The owner must verify the Billing page literally says **Free Trial**,
   and must never select **Upgrade**. A normal paid Cloud Billing account
   plus Cloud Run spend caps is not a strict zero-charge guarantee.
2. **Oracle OCI Always Free (longer-term candidate):** up to 2 Arm OCPUs
   and 12 GiB RAM aggregate on eligible Always Free tenancy, without
   paid-account upgrade; instance capacity is not guaranteed and idle
   instances may be reclaimed. Python ONNX/OpenCV Arm compatibility and
   isolated synthetic OCR must be proven *before* migrating the fallback.
   This repository only implements the Google Cloud Run transport today.
3. **Offline handset path (always preferred):** local Samsung ML Kit and
   Accessibility text remain first, keeping images on the device as far as
   possible and avoiding provider billing and remote image access.

For every path, preserve the disabled default and local ten-item evidence
gate. Do not allow Google billing to be linked or a container deployed
solely because a provider has a recurring Free Tier: free allowance,
alerts-only budgets and spend caps are not a hard EUR 0 safeguard.

References:
- https://cloud.google.com/signup-faqs
- https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
- https://docs.oracle.com/de-de/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

**Staging only; NOT deployed or enabled.** This is not an additional always-on
Bob trading service. Its only role is to read an existing DEGIRO screenshot
when the authenticated handset path cannot supply appText/local ML Kit and
the Render OCR child cannot safely start or exceeds its cgroup limit.

Provider candidate: Google Cloud Run (not the connected Google Drive app).
Plan for 2 GiB memory, 1 vCPU, request concurrency 1, minimum instances 0,
maximum instances 1, request timeout 90 seconds, no persistent disk, no
database. The pinned native OCR remains inside a network-denied child
(seccomp). No API-based paid OCR, no new market sources, no trades.

## Important before ANY deployment

* Cloud Run's monthly free grants are **not a hard spending cap**. Billing,
  container image registry, log volume, networking or excess use may cost
  money. An unauthenticated public Cloud Run URL can be abused to incur
  charges even if application-layer bearer checks reject requests. Use
  provider IAM / approved private ingress and enforce budgets/quotas; first
  independently test authentication end-to-end. In Cloud Billing create a
  **Spend cap enforcement** budget specifically scoped to the Cloud Run
  service in the one OCR project (NOT an alerts-only budget), plus request
  quotas and max instances=1. Confirm the cap is supported and enforced
  in the actual billing account before ANY production traffic. Enforcement
  is not instantaneous: overages can still be billed, and the Cloud Run
  cap does not cover other products such as image registries, builds, or
  certain networking resources. Do not promise absolute zero expense.
  See https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
  and https://docs.cloud.google.com/run/docs/configuring/billing-settings .
  This repository does **not** run `gcloud` or create paid resources.
* The existing Render app and Google Drive connection **do not grant Google
  Cloud Run project ownership or deployment permissions**. Cloud-account
  authorization must be completed using an eligible project/connector. Cloud
  Run must enforce IAM (`--no-allow-unauthenticated`). Grant `roles/run.invoker`
  on this specific service only to a dedicated service account, with no
  broader project/admin permissions. A separately stored provider-account
  credential in Render `BOB_REMOTE_OCR_GCP_SA_JSON` is used to mint a
  short-lived identity token for the Cloud Run audience. Do not copy the
  credential into GitHub/Chat/logs. Rotate or revoke after testing.
* Never commit or paste a Cloud Run token, screenshot or device ID. Secrets
  must be entered through the provider's secure secret manager and Render's
  environment manager. Do not put private values into GitHub Actions logs.
* **Zero-cost lock (default)**: even if `BOB_REMOTE_OCR_ENABLED=true`, Bob
  rejects all off-box OCR requests unless a separate variable
  `BOB_REMOTE_OCR_COST_POLICY=metered_risk_explicitly_accepted` is deliberately
  set. Under the owner requirement of **no additional charges**, never set
  this cost-risk acceptance variable. This is a Bob-side remote-request lock,
  **not** a general Google billing guarantee. Keep the Google project unlinked
  from billing for the only current hard prevention of billable Cloud Run
  use; in that state Cloud Run cannot run.
* Offload is disabled by default (`BOB_REMOTE_OCR_ENABLED` absent or false).
  It requires `BOB_REMOTE_OCR_URL` at HTTPS `*.a.run.app/ocr`,
  `BOB_REMOTE_OCR_GCP_SA_JSON` stored as a protected Render secret (Google
  service-account ID-token credential) and a distinct secret of at least
  32 characters (`BOB_REMOTE_OCR_TOKEN`) on **both** ends. Cloud Run IAM
  verifies the ID token before container execution; the service also checks
  the secondary `X-Bob-Ocr-Key` header. Do not enable merely because an
  endpoint responds: first prove IAM, bounded abuse/cost controls, rollback,
  failure isolation, genuine original-image matching and 10 unique products.
* Cloud Run is a **fallback**, not guaranteed realtime. Scale-to-zero
  introduces cold starts. If it times out, is unreachable, lacks quota or
  returns malformed results, the current Render import stays waiting-memory
  / read-failed; previous confirmed lists remain untouched.
* No capture is made here. The remote endpoint receives only one original
  PNG (no portfolio, token, account state, price cache or entire batch),
  never records request bodies, and returns two or three optical text passes.
  Existing local JS parser must still independently validate exact ten
  products and their original timestamps. Remote OCR is not an independent
  broker quote or trade authorization.

Before enabling, run isolated synthetic-image integration tests and
measure cold/warm latency, per-image RAM, Cloud Run quota and billing on the
actual provider. Record evidence in existing GitHub issue #1308 (original
RAM problem) / #1329 (cost/security). Never change the 505-MiB local kill
threshold just to force successful imports.

Official provider limits:
https://cloud.google.com/run/pricing
https://docs.cloud.google.com/run/docs/configuring/instances/memory-limits
