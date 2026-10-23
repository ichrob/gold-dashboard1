"""Configuration contract only. Does not claim Render account settings were applied."""
from pathlib import Path
import re
import unittest

BASE=Path(__file__).resolve().parent

class ReleaseGateConfigurationTests(unittest.TestCase):
    def test_blueprint_waits_for_git_checks(self):
        render=(BASE/'render.yaml').read_text()
        self.assertRegex(render,r'(?m)^\s+autoDeployTrigger:\s+checksPass\s*$')
        self.assertNotRegex(render,r'(?m)^\s+autoDeployTrigger:\s+commit\s*$')
        self.assertIn('healthCheckPath: /health',render)

    def test_push_main_requires_complete_validation(self):
        workflow=(BASE/'.github/workflows/ci.yml').read_text()
        self.assertIn('name: Bob CI',workflow)
        self.assertIn('pull_request:',workflow)
        self.assertIn('branches:',workflow)
        self.assertIn('  release-gate:',workflow)
        self.assertIn('needs: [validate]',workflow)
        self.assertIn('github.event_name == \'push\'',workflow)
        self.assertIn("github.ref == 'refs/heads/main'",workflow)
        self.assertIn('VALIDATE_RESULT: ${{ needs.validate.result }}',workflow)
        self.assertIn('if [ "$VALIDATE_RESULT" != "success" ]; then',workflow)
        self.assertNotIn('\\${{',workflow)

    def test_deployed_degiros_js_check_cannot_block_render(self):
        workflow=(BASE/'.github/workflows/bob-degiro-deployed-js.yml').read_text()
        self.assertIn('workflow_dispatch:',workflow)
        self.assertIn('schedule:',workflow)
        self.assertNotIn('  push:',workflow)
        self.assertNotIn('  workflow_run:',workflow)
        self.assertIn('sha256sum degiro_assistant.js',workflow)
        self.assertIn('sha256sum /tmp/deployed-degiro.js',workflow)

    def test_quote_sources_and_trading_stay_separate(self):
        shared=(BASE/'product_evidence_contract.js').read_text()
        scanner=(BASE/'degiro_all_products.js').read_text()
        workspace=(BASE/'bob_unified_workspace.js').read_text()
        self.assertIn('tradeable:false,automaticOrder:false',shared)
        self.assertIn('executableQuote:false',shared)
        self.assertIn('contract.fromCombined(x,now)',scanner)
        self.assertIn("require('./product_evidence_contract.js')",workspace)

if __name__=='__main__':unittest.main()
