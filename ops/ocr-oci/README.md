# Bob OCR – Oracle OCI Always Free (ARM64), STAGING ONLY

This branch replaces the previously proposed Google Cloud Run fallback with a
single Oracle **VM.Standard.A1.Flex / ARM64** virtual machine, and intentionally
creates **no new cloud resources**. An Oracle VM is not yet provisioned.
The preferred path is still Samsung on-device ML Kit / appText.

## Cost and provider gate (strict)
- Only use an account that shows **Always Free**. Never upgrade to **Pay As You Go**.
  Oracle may require a real credit/debit card for identity validation and place
  a temporary authorization hold, not a final charge. Do not enter any card,
  password, SSH private key, or OCR secret into GitHub issues or this chat.
- OCI official allowances as of November 2026: **2 OCPUs and 12 GB of RAM total**
  for Always Free Ampere A1 (1,500 OCPU-hours / 9,000 GB-hours each month),
  plus 200 GB Always Free block volume. Do not trust older 4 OCPU/24 GB guides.
- Choose **1 OCPU, 4 GB RAM, 50 GB boot volume**, one Always-Free-eligible
  Ubuntu ARM64 VM in the **home region**; keep within all other quotas.
  Verify the instance, boot volume and network all say **Always Free eligible**.
  Do not add paid instances, load balancers, logging or storage.
- A1 free capacity may be unavailable. Try another availability domain or stop.
  **Never solve a capacity error by choosing a paid shape or upgrading.**
  Oracle may reclaim prolonged idle VMs; this does not justify artificial
  keepalive traffic or any upgrade. No 24/7 availability or trading guarantee.
- The project never invokes OCI provisioning APIs, purchases, account
  upgrades, paid scaling or live orders. Existing Render cgroup limits,
  market signals and original PNG archives are unchanged.

Sources:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm
- https://www.oracle.com/cloud/free/faq/

## Owner account setup (account action, not automated here)

1. Open https://signup.oraclecloud.com/ . Select the correct home country,
   verify email and complete Oracle's identity verification. Do not sign up
   for a second account if already registered.
2. In the authenticated OCI Console, choose **Compute → Instances → Create**.
   Pick the Ampere A1 Flex shape **only if explicitly Always Free eligible**,
   with 1 OCPU and 4 GB RAM; use an ARM64-compatible Linux image and a
   50-GB Always Free boot volume. Keep all user account secrets private.
3. Configure network security so **only TCP 8443** is open for OCR and SSH
   is restricted to the owner's trusted source. Prefer a narrow allowlist
   of Render's verified egress addresses for TCP 8443. Do not expose any
   plaintext port or the internal Python server without TLS. No new
   public IP purchase and no load balancer.
4. After the instance exists, record its public IPv4 address for your own
   setup. Do not publish original image data or OCR secrets.
5. Before enabling Bob's remote OCR, prove the running VM has the intended
   Always-Free shape, 1 OCPU/4 GB, no added paid resources, a functioning
   ARM64 build, and a verified TLS connection.

## Connection without buying a domain or a Cloudflare plan

The currently connected Cloudflare account has no managed DNS zones. A
production Cloudflare Tunnel needs a domain under Cloudflare, so it is not
assumed here. Instead, a single OCI VM can expose HTTPS on its **public IPv4
port 8443**, with a self-signed, IP-SAN server certificate. Bob explicitly
trusts **only that certificate**, and Python checks the original peer's IP
subjectAltName via the standard TLS verifier. There are no HTTP redirects.

On the VM, using an administrator's SSH session, create a dedicated private
secrets directory. For the example commands below, replace `PUBLIC_IP` with
the actual Oracle public IP:

```sh
sudo install -d -m 700 /opt/bob-ocr/secrets
PUBLIC_IP="your.actual.public.ip"
sudo openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
  -keyout /opt/bob-ocr/secrets/tls.key \
  -out /opt/bob-ocr/secrets/tls.crt \
  -subj "/CN=bob-ocr" -addext "subjectAltName=IP:${PUBLIC_IP}"
sudo chown 65532:65532 /opt/bob-ocr/secrets/tls.key /opt/bob-ocr/secrets/tls.crt
sudo chmod 400 /opt/bob-ocr/secrets/tls.key
sudo chmod 444 /opt/bob-ocr/secrets/tls.crt
```

Generate a separate random key in the VM's own protected secret manager or
root-owned env file, not in this chat. Store it as `BOB_REMOTE_OCR_TOKEN`;
its length must be 32–256 printable ASCII characters. Rotate on compromise.
The server never sends it back in HTTP responses.

A successful TLS handshake may be checked *without* sending images:

```sh
openssl s_client -connect PUBLIC_IP:8443 -verify_ip PUBLIC_IP \
  -CAfile /opt/bob-ocr/secrets/tls.crt
```

Do not treat a merely reachable URL as proof. Certificate expiry, changed
VM IP, and lost private key must fail closed. Renew and re-verify the client
trust explicitly.

## Build only after the owner has created a verified Always Free VM

The repo is public, so only source code and pinned dependency names are
downloaded; no credentials or private DEGIRO images are needed:

```sh
git clone --depth 1 --branch fix/ocr-oracle-always-free \
  https://github.com/ichrob/gold-dashboard1.git bob-ocr-src
cd bob-ocr-src
docker build --platform linux/arm64 -f ops/ocr-oci/Dockerfile -t bob-ocr-oci:staging .
docker run --rm --platform linux/arm64 --entrypoint python \
  bob-ocr-oci:staging ops/ocr-oci/smoke.py
```

The image runs a non-root user. Before starting, place a root-protected
env file with the random token at `/opt/bob-ocr/secrets/ocr.env` (mode 600),
then start the isolated container with an explicit 3 GiB cgroup limit on
the 4 GB VM, `--cpus=0.9`, `--pids-limit=128`, no privileged mode,
no Linux capabilities, a read-only root, small temporary filesystem and
read-only cert/key mounts. The OCI security rules expose only 8443.
The OCR child additionally uses seccomp to block socket/network calls.

Do not run a public Docker image registry or add a paid resource just to
deploy. The app is single-request HTTPServer, no background OCR scheduler,
no image logging and no persisted screenshots.

## Render client gate – remains DISABLED

Existing `remote_ocr_fallback.py` supports a single OCI address, with:
- `BOB_REMOTE_OCR_URL=https://PUBLIC_IP:8443/ocr`
- `BOB_REMOTE_OCR_ALLOWED_IP=PUBLIC_IP` (must match the URL and be global IPv4)
- `BOB_REMOTE_OCR_TLS_CA_PEM` containing only the **public** server certificate
- `BOB_REMOTE_OCR_TOKEN` (same protected app key)
- `BOB_REMOTE_OCR_COST_POLICY=oci_always_free_verified` only **after**
  provider Always Free acceptance has been proved, never on a paid account
- `BOB_REMOTE_OCR_ENABLED=true` **last**, after full private acceptance

Until both of the last two switches have explicit validated values, **zero
outbound OCR network requests** occur. Never store secrets in repository code
or chat. An HTTP failure, invalid TLS chain or IP mismatch, a mismatched
image hash, missing two-pass agreement or a failed 10-ISIN parser preserves
the previous fail-closed `waiting-memory` / `read-failed` semantics.

Remote OCR is not a second original price source, not evidence of DEGIRO
account eligibility, and not a trading or order permission.

## Acceptance, rollback and scope

1. All GitHub Python + JavaScript + CodeQL/Risk checks pass on this SHA.
2. GitHub native ARM64 job builds and executes the real OCR engine using
   **only a synthetic screenshot**. This does not start Oracle VM.
3. Test the VM's image under real 4 GB RAM; prove valid TLS IP/cert and
   wrong-key rejection with synthetic content. Measure OCR peak, latency,
   timeout and memory limits.
4. Only then permit exactly one consented original DEGIRO import and prove
   10 distinct rows, original source timestamps and correct provenance.
5. If the Oracle VM is reclaimed, offline or out of resource capacity, Bob
   must continue its original local route without any dependency on Oracle.
6. Rollback: unset `BOB_REMOTE_OCR_ENABLED` and remove the OCI secret
   configuration from Render after retaining the necessary audit proofs.
   No live trading code changes or data deletion.

**Status:** preparation only. No OCI credentials, account, VM, DNS, service
token or paid resource was created from this ChatGPT session.
