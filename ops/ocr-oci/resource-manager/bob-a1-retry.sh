#!/usr/bin/env bash
# Run from the owner's OCI Cloud Shell. Only retry the reviewed single-VM plan.
set -Eeuo pipefail
umask 077
export OCI_CLI_REGION=eu-zurich-1
cd "$HOME"
exec 9>.bob-a1.lock
flock -n 9 || { echo 'Die Startautomatik läuft bereits.'; exit 0; }
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
trap 'echo "Angehalten bei Zeile $LINENO. Siehe vorherige Meldung."' ERR
rmjob=(oci resource-manager job)
rows='(.data | if type == "array" then . else .items end)'
root=$(oci iam availability-domain list --all | jq -er '.data[0]["compartment-id"]')
bob=$(oci iam compartment list --compartment-id "$root" --name BobOCR --lifecycle-state ACTIVE --all | jq -er '.data | select(length==1) | .[0].id')
stack=$(oci resource-manager stack list --compartment-id "$bob" --all |
  jq -er "$rows"' | map(select(."display-name"=="BobOCR-Zuerich-Plan" and ."lifecycle-state"=="ACTIVE")) | select(length==1) | .[0].id')
wait_job() {
  local state
  while true; do
    state=$("${rmjob[@]}" get --job-id "$1" --query 'data."lifecycle-state"' --raw-output)
    case "$state" in
      ACCEPTED|IN_PROGRESS|CANCELING) sleep 15 ;;
      *) echo "$state"; return ;;
    esac
  done
}
while true; do
  date -Is
  instances=$(oci compute instance list --compartment-id "$bob" --all)
  if jq -e '[.data[] | select(."display-name"=="bob-ocr-zurich" and ."lifecycle-state"!="TERMINATED")] | length>0' <<<"$instances" >/dev/null; then
    echo 'Bob-Instanz vorhanden. Kein weiterer Startversuch.'
    exit 0
  fi
  jobs=$("${rmjob[@]}" list --stack-id "$stack" --all)
  if jq -e "$rows"' | any(.[]; ."lifecycle-state" | IN("ACCEPTED","IN_PROGRESS","CANCELING"))' <<<"$jobs" >/dev/null; then
    echo 'Stack beschäftigt. Prüfe in fünf Minuten erneut.'
    sleep 300
    continue
  fi
  plan=$("${rmjob[@]}" create-plan-job --stack-id "$stack" --display-name Bob-A1-Startplan --query data.id --raw-output)
  [[ $(wait_job "$plan") == SUCCEEDED ]] || { echo 'Plan fehlgeschlagen. Automatik angehalten.'; exit 1; }
  rm -f "$work/plan.json"
  "${rmjob[@]}" get-job-tf-plan --job-id "$plan" --tf-plan-format JSON --file "$work/plan.json"
  # Only the missing private VM can be created. No network, replacement or deletion.
  jq -e --arg bob "$bob" '
    [.resource_changes[] | select(.mode=="managed" and .change.actions!=["no-op"])] |
    length==1 and (.[0] | .address=="oci_core_instance.bob" and .change.actions==["create"] and
      (.change.after | .compartment_id==$bob and .display_name=="bob-ocr-zurich" and
      (.availability_domain|ascii_upcase|endswith(":EU-ZURICH-1-AD-1")) and
      .shape=="VM.Standard.A1.Flex" and (.shape_config[0].ocpus|tonumber)==1 and
      (.shape_config[0].memory_in_gbs|tonumber)==4 and
      (.source_details[0].boot_volume_size_in_gbs|tonumber)==50 and
      (.source_details[0].boot_volume_vpus_per_gb|tonumber)==10 and
      .source_details[0].source_type=="image" and
      (.create_vnic_details[0].assign_public_ip|tostring)=="false"))' "$work/plan.json" >/dev/null ||
    { echo 'Plan weicht vom erwarteten Start einer einzelnen Bob-VM ab. Angehalten.'; exit 1; }
  # Verify the account-reviewed platform image against the image actually resolved in this plan.
  image=$(jq -er '.resource_changes[] | select(.address=="oci_core_instance.bob") | .change.after.source_details[0].source_id' "$work/plan.json")
  oci compute image get --image-id "$image" | jq -e '.data | ."compartment-id"==null and ."display-name"=="Canonical-Ubuntu-24.04-aarch64-2026.11.05-0"' >/dev/null
  apply=$("${rmjob[@]}" create-apply-job --stack-id "$stack" --execution-plan-strategy "$plan" --display-name Bob-A1-Start --query data.id --raw-output)
  state=$(wait_job "$apply")
  case "$state" in
    SUCCEEDED) echo 'Bereitstellung erfolgreich. Automatik beendet.'; exit 0 ;;
    FAILED)
      logs=$("${rmjob[@]}" get-job-logs --job-id "$apply" --all)
      if jq -e '[.. | objects | .message? | strings | select(test("Error:";"i"))] |
        length>0 and all(.[]; test("out of host capacity";"i"))' <<<"$logs" >/dev/null; then
        echo 'Zürich ausgelastet. Neuer Versuch in 30 Minuten.'
        sleep 1800
      else
        echo 'Anderer Fehler beim Start. Details im Auftrag Bob-A1-Start.'
        exit 1
      fi ;;
    *) echo "Startauftrag endete mit $state."; exit 1 ;;
  esac
done
