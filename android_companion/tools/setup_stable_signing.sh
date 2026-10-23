#!/usr/bin/env bash
# One-time, device-local setup for Bob's permanent Android signing identity.
# Run only on a trusted machine/Termux with Java keytool and GitHub CLI.
# NEVER upload or commit the private keystore. No passwords are printed.
set -euo pipefail
umask 077

repo="ichrob/gold-dashboard1"
alias_name="bob-stable"
dir="${HOME}/.bob-private-android-signing"
file="${dir}/bob-stable.p12"

for executable in gh keytool base64 tr sed; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    echo "Missing required tool: $executable" >&2
    exit 1
  fi
done
gh auth status >/dev/null
mkdir -p "$dir"
chmod 700 "$dir"
if [ -e "$file" ]; then
  # An interrupted GitHub upload can be resumed with the SAME signing key.
  # Never overwrite it or silently rotate the stable Android identity.
  echo "Reusing the existing private signing key; no new key will be generated."
fi

printf 'Choose a strong password (keep it in a password manager): '
IFS= read -rs password
printf '\n'
if [ "${#password}" -lt 20 ] || [[ "$password" == *$'\n'* ]] || [[ "$password" == *$'\r'* ]]; then
  echo "Password must be at least 20 characters and one line." >&2
  exit 1
fi
printf 'Repeat the password: '
IFS= read -rs confirm
printf '\n'
if [ "$password" != "$confirm" ]; then
  echo "Passwords do not match." >&2
  exit 1
fi
unset confirm

# PKCS12 protects the private key; a matching store/key password is used
# to simplify the one-time mobile setup. The key stays on this device.
if [ ! -e "$file" ]; then
  keytool -genkeypair -noprompt -keystore "$file" -storetype PKCS12 \
    -alias "$alias_name" -keyalg RSA -keysize 3072 -validity 10000 \
    -dname "CN=Bob Private Android, OU=Bob, O=Private Application" \
    -storepass "$password" -keypass "$password" >/dev/null
fi
chmod 600 "$file"

fingerprint="$(keytool -list -v -keystore "$file" -storepass "$password" \
    -alias "$alias_name" 2>/dev/null \
    | sed -n 's/^[[:space:]]*SHA256: //p' | head -n 1 | tr -d ':[:space:]')"
if ! [[ "$fingerprint" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "Could not verify the certificate fingerprint; key remains local." >&2
  exit 1
fi
existing_pin="$(gh variable get BOB_ANDROID_CERT_SHA256 -R "$repo" 2>/dev/null || true)"
if [ -n "$existing_pin" ]; then
  normalized_pin="$(printf '%s' "$existing_pin" | tr '[:lower:]' '[:upper:]' | tr -d ':[:space:]')"
  normalized_cert="$(printf '%s' "$fingerprint" | tr '[:lower:]' '[:upper:]' | tr -d ':[:space:]')"
  if [ "$normalized_pin" != "$normalized_cert" ]; then
    echo "Signing identity conflict: GitHub's existing fingerprint differs." >&2
    echo "STOP. Do not replace the old signing key or publish incompatible updates." >&2
    exit 1
  fi
fi

# Use stdin so no large keystore or passwords appear in git, command arguments
# or shell history. GitHub encrypts repository Actions secrets on receipt.
base64 "$file" | tr -d '\n' | gh secret set BOB_ANDROID_KEYSTORE_BASE64 -R "$repo"
printf '%s' "$password" | gh secret set BOB_ANDROID_STORE_PASSWORD -R "$repo"
printf '%s' "$alias_name" | gh secret set BOB_ANDROID_KEY_ALIAS -R "$repo"
printf '%s' "$password" | gh secret set BOB_ANDROID_KEY_PASSWORD -R "$repo"
gh variable set BOB_ANDROID_CERT_SHA256 -R "$repo" --body "$fingerprint"
unset password

echo "GitHub signing secrets configured. Fingerprint verified locally."
echo "IMPORTANT: Back up $file securely (encrypted), separately from its password."
echo "Without the original private key, future updates to this installed app cannot be signed."
echo "Only after secure backup, manually run workflow: Bob Android – dauerhafte signierte App."
