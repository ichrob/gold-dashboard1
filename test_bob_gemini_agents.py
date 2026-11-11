"""Static guardrails for the three Bob Antigravity read-only specialists."""
from pathlib import Path
import unittest


ROOT = Path(__file__).parent / ".agents" / "agents"
AGENTS = ("bob-source-investigator.md", "bob-paper-study-auditor.md",
          "bob-security-reviewer.md")
READ_TOOLS = {"view_file", "grep_search", "find_by_name"}


def frontmatter(path):
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n") or raw.count("\n---\n") != 1:
        raise ValueError("invalid-agent-frontmatter")
    header = raw.split("\n---\n", 1)[0][4:]
    lines = header.splitlines()
    attrs = {}
    tools = []
    current = None
    for line in lines:
        if line.startswith("  - "):
            if current != "tools":
                raise ValueError("unrecognized-list")
            tools.append(line[4:])
        elif ":" in line and not line.startswith(" "):
            name, value = line.split(":", 1)
            attrs[name] = value.strip()
            current = name
        else:
            raise ValueError("unrecognized-frontmatter")
    return attrs, tools


class AgentSafety(unittest.TestCase):
    def test_independent_agents_are_read_only_without_mcp_or_shell(self):
        self.assertEqual(sorted(x.name for x in ROOT.glob("*.md")),
                         sorted(AGENTS))
        for name in AGENTS:
            with self.subTest(agent=name):
                attrs, tools = frontmatter(ROOT / name)
                self.assertEqual(attrs.get("name"), name[:-3])
                self.assertEqual(attrs.get("commandExecutionPolicy"), "off")
                self.assertEqual(attrs.get("inheritMcp"), "false")
                self.assertEqual(attrs.get("subagent"), "true")
                self.assertTrue(tools)
                self.assertTrue(set(tools) <= READ_TOOLS)
                self.assertNotIn("run_command", tools)
                self.assertNotIn("call_mcp_tool", tools)

    def test_public_inert_draft_workflow_requires_owner_and_manual_trigger(self):
        wf = (Path(__file__).parent / ".github" / "workflows" /
              "bob-gemini-independent-draft.yml").read_text()
        self.assertIn("workflow_dispatch:", wf)
        self.assertNotIn("\n  pull_request:", wf)
        self.assertNotIn("\n  push:", wf)
        self.assertIn("github.actor == 'ichrob'", wf)
        self.assertIn("BOB_GEMINI_DRAFT_PR_ENABLED:", wf)
        self.assertIn("gemini_independent_draft.py", wf)
        self.assertNotIn("dangerously-skip-permissions", wf)


if __name__ == "__main__":
    unittest.main()
