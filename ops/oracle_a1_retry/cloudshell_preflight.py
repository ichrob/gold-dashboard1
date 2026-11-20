#!/usr/bin/env python3
"""Read-only Oracle Cloud Shell preflight for Bob's existing OCI Resource Manager stack.

Never runs Terraform apply/plan, creates API keys, or changes OCI or Cloudflare.
Outputs only bounded diagnostic classifications; never raw plans or logs.
Run from an Oracle Cloud Shell opened with Zurich region selected:
  python3 bob_oracle_cloudshell_preflight.py ocid1.ormstack.oc1.eu-zurich-1.<id>
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REGION = 'eu-zurich-1'
REVIEWED_IMAGE = 'ocid1.image.oc1.eu-zurich-1.aaaaaaaadk22jaklt42vd4entg5pfsn5jfwbakrs7nsrawqvv5ya7iefhgiq'
CAPACITY = re.compile(r'out.of.host.capacity|outofhostcapacity|no.capacity.for.shape|shape.{0,100}capacity.{0,100}not.available|capacity.{0,100}not.available', re.I | re.S)


class CliUnavailable(Exception):
    pass


def call(*args, output_file=None):
    argv = ['oci', *args, '--region', REGION]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise CliUnavailable('OCI_CLI_NOT_AVAILABLE_OR_TIMEOUT') from ex
    if p.returncode != 0:
        # Never emit stderr; it can contain account IDs or other sensitive context.
        raise CliUnavailable('OCI_COMMAND_REJECTED')
    if output_file:
        return None
    return p.stdout


def parse_json(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError) as ex:
        raise CliUnavailable('OCI_RESPONSE_NOT_JSON') from ex


def one(details):
    if isinstance(details, list):
        return details[0] if len(details) == 1 and isinstance(details[0], dict) else {}
    return details if isinstance(details, dict) else {}


def valid_plan(plan):
    if not isinstance(plan, dict):
        return False, 'JSON_NOT_AN_OBJECT'
    changes = plan.get('resource_changes')
    if not isinstance(changes, list) or not changes:
        return False, 'NO_RESOURCE_CHANGES'
    creates = []
    for r in changes:
        if not isinstance(r, dict):
            return False, 'INVALID_CHANGE'
        actions = r.get('change', {}).get('actions')
        if not isinstance(actions, list):
            return False, 'UNKNOWN_ACTION'
        if actions == ['no-op'] or actions == ['read']:
            continue
        if actions != ['create']:
            return False, 'UNEXPECTED_UPDATE_OR_DELETION'
        creates.append(r)
    if len(creates) != 1 or creates[0].get('address') != 'oci_core_instance.bob':
        return False, 'UNEXPECTED_NEW_RESOURCES'
    r = creates[0]
    if r.get('type') != 'oci_core_instance' or r.get('mode') != 'managed':
        return False, 'INCORRECT_INSTANCE_RESOURCE'
    after = r.get('change', {}).get('after')
    if not isinstance(after, dict):
        return False, 'UNKNOWN_INSTANCE_CONFIGURATION'
    shape = one(after.get('shape_config'))
    source = one(after.get('source_details'))
    vnic = one(after.get('create_vnic_details'))
    options = one(after.get('instance_options'))
    try:
        size_ok = (float(shape.get('ocpus', -1)) == 1 and
                   float(shape.get('memory_in_gbs', -1)) == 4 and
                   float(source.get('boot_volume_size_in_gbs', -1)) == 50 and
                   float(source.get('boot_volume_vpus_per_gb', -1)) == 10)
    except (TypeError, ValueError):
        size_ok = False
    if not size_ok or after.get('shape') != 'VM.Standard.A1.Flex':
        return False, 'NOT_REVIEWED_A1_FREE_CONFIGURATION'
    if source.get('source_type') != 'image' or source.get('source_id') != REVIEWED_IMAGE:
        return False, 'IMAGE_DOES_NOT_MATCH_REVIEWED_BUILD'
    if vnic.get('assign_public_ip') is not False:
        return False, 'PUBLIC_IP_NOT_PROHIBITED'
    if options.get('are_legacy_imds_endpoints_disabled') is not True:
        return False, 'METADATA_SECURITY_NOT_CONFIRMED'
    if not str(after.get('availability_domain', '')).upper().endswith(':EU-ZURICH-1-AD-1'):
        return False, 'NOT_ZURICH_AD1'
    return True, 'CONFIGURATION_MATCHES_REVIEWED_PLAN'


def main(stack):
    if not re.fullmatch(r'ocid1\.ormstack\.oc1\.eu-zurich-1\.[a-z0-9]+', stack):
        print('RESULT=INVALID_ZURICH_STACK_ID')
        return 2
    print('MODE=READ_ONLY')
    print('AUTOMATIC_APPLY_ALLOWED=NO')
    print('ACCOUNT_ALWAYS_FREE=UNVERIFIED')
    print('REGION=' + REGION)
    try:
        stack_data = parse_json(call('resource-manager', 'stack', 'get', '--stack-id', stack))['data']
        if stack_data.get('id') != stack:
            print('RESULT=STACK_NOT_VERIFIED')
            return 3

        # Compare live Compute inventory with Terraform state. Historical snapshots
        # can say ABSENT while the compartment still contains an unmanaged A1.
        # This script does not start, stop, change or delete anything.
        compartment = stack_data.get('compartment-id')
        if not isinstance(compartment, str) or not re.fullmatch(r'ocid1\.compartment\.oc1\.[a-z0-9.]+', compartment):
            print('RESULT=INVALID_STACK_COMPARTMENT')
            return 3
        live_status = 'UNAVAILABLE'
        try:
            raw_compute = parse_json(call('compute', 'instance', 'list',
                                          '--compartment-id', compartment, '--all'))
            instances = raw_compute.get('data', [])
            if not isinstance(instances, list):
                raise CliUnavailable('INVALID_COMPUTE_LIST')
            active = [x for x in instances if isinstance(x, dict)
                      and x.get('lifecycle-state') not in ('TERMINATED',)
                      and (x.get('display-name') == 'bob-ocr-zurich'
                           or x.get('shape') == 'VM.Standard.A1.Flex')]
            if len(active) == 0:
                live_status = 'ABSENT'
            elif len(active) == 1:
                lifecycle = active[0].get('lifecycle-state')
                live_status = ('ONE_RUNNING' if lifecycle == 'RUNNING' else
                               'ONE_STOPPED' if lifecycle == 'STOPPED' else 'ONE_OTHER_STATE')
            else:
                live_status = 'MULTIPLE'
        except CliUnavailable:
            pass
        print('COMPUTE_INSTANCE=' + live_status)
        state_status = 'UNAVAILABLE'
        try:
            with tempfile.TemporaryDirectory(prefix='bob_oci_state_ro_') as state_folder:
                state_file = Path(state_folder) / 'tfstate.json'
                call('resource-manager', 'stack', 'get-stack-tf-state', '--stack-id', stack,
                     '--file', str(state_file), output_file=state_file)
                state_data = parse_json(state_file.read_text(encoding='utf-8'))
                resources = state_data.get('resources')
                if isinstance(resources, list):
                    vm = [x for x in resources if isinstance(x, dict)
                          and x.get('mode') == 'managed' and x.get('type') == 'oci_core_instance'
                          and isinstance(x.get('instances'), list) and len(x['instances']) > 0]
                    state_status = 'PRESENT' if vm else 'ABSENT'
                else:
                    state_status = 'INVALID'
        except (CliUnavailable, OSError, KeyError, ValueError):
            pass
        print('TERRAFORM_STATE_INSTANCE=' + state_status)
        print('COMPUTE_TF_DISAGREEMENT=' + str(
            (live_status in ('ONE_RUNNING', 'ONE_STOPPED', 'ONE_OTHER_STATE', 'MULTIPLE')
             and state_status == 'ABSENT') or
            (live_status == 'ABSENT' and state_status == 'PRESENT')).lower())
        raw_jobs = parse_json(call('resource-manager', 'job', 'list', '--stack-id', stack, '--all'))
        jobs = raw_jobs.get('data', [])
        if not isinstance(jobs, list):
            raise CliUnavailable('INVALID_JOB_LIST')
        print('JOBS=' + str(len(jobs)))
        applies = sorted([j for j in jobs if j.get('operation') == 'APPLY'], key=lambda j:j.get('time-created', ''), reverse=True)
        plans = sorted([j for j in jobs if j.get('operation') == 'PLAN' and j.get('lifecycle-state') == 'SUCCEEDED'], key=lambda j:j.get('time-created', ''), reverse=True)
        last = applies[0] if applies else {}
        print('LATEST_APPLY_STATUS=' + (last.get('lifecycle-state') or 'NONE'))
        if last.get('lifecycle-state') == 'FAILED' and last.get('id'):
            try:
                log = call('resource-manager', 'job', 'get-job-logs-content', '--job-id', last['id'])
                print('LAST_APPLY_FAILURE=' + ('HOST_CAPACITY' if CAPACITY.search(log[-150000:]) else 'OTHER_OR_UNKNOWN'))
            except CliUnavailable:
                print('LAST_APPLY_FAILURE=LOG_UNAVAILABLE')
        elif last.get('lifecycle-state') == 'SUCCEEDED':
            print('LAST_APPLY_FAILURE=NONE')
        else:
            print('LAST_APPLY_FAILURE=NOT_ESTABLISHED')
        if not plans:
            print('LATEST_SUCCESSFUL_PLAN=NONE')
            print('PLAN_CONFIGURATION=UNVERIFIED')
            print('RESULT=PLAN_REQUIRED')
            return 0
        print('LATEST_SUCCESSFUL_PLAN=FOUND')
        # GetJobTfPlan returns a stream. Parse it locally and never disclose the raw plan.
        with tempfile.TemporaryDirectory(prefix='bob_oci_ro_') as folder:
            path = Path(folder) / 'tfplan.json'
            try:
                call('resource-manager', 'job', 'get-job-tf-plan', '--job-id', plans[0]['id'], '--tf-plan-format', 'JSON', '--file', str(path), output_file=path)
                verified, reason = valid_plan(parse_json(path.read_text(encoding='utf-8')))
            except (CliUnavailable, OSError):
                verified, reason = False, 'PLAN_UNAVAILABLE'
        print('PLAN_CONFIGURATION=' + reason)
        print('ACCOUNT_FREE_TIER_STATUS=NOT_VERIFIABLE_FROM_PLAN')
        print('RESULT=' + ('PLAN_CONFIG_CHECKED_ACCOUNT_REVIEW_PENDING' if verified else 'PLAN_REJECTED'))
        return 0
    except CliUnavailable as error:
        print('RESULT=' + str(error))
        return 3
    except (KeyError, TypeError, ValueError):
        print('RESULT=UNEXPECTED_OCI_RESPONSE')
        return 3


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python3 bob_oracle_cloudshell_preflight.py <existing-Zurich-stack-OCID>')
        sys.exit(2)
    sys.exit(main(sys.argv[1]))