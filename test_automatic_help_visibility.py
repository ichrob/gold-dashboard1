"""Legacy report exporters remain internal; no visible manual handoff controls."""
import unittest
from html.parser import HTMLParser
import bob_problems, bob_self_healing, degiro_product_audit_panel

class Visibility(HTMLParser):
    def __init__(self):
        super().__init__();self.stack=[];self.visible=[];self.hidden_ids=set();self.visible_ids=set()
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);hidden=any(self.stack) or 'hidden' in attrs
        if 'id' in attrs:(self.hidden_ids if hidden else self.visible_ids).add(attrs['id'])
        if tag not in ('br','input','meta','link','img','hr'):self.stack.append(hidden or tag=='script')
    def handle_endtag(self,tag):
        if self.stack:self.stack.pop()
    def handle_data(self,data):
        if not any(self.stack):self.visible.append(data)

class AutomaticHelpVisibility(unittest.TestCase):
    def test_private_legacy_controls_hidden_but_product_warning_visible(self):
        for module,ids in [(bob_problems,('bobProblemsShare','bobProblemsCopy')),(bob_self_healing,('bobHealingCopy','bobHealingReport')),(degiro_product_audit_panel,('bobAuditShareChatGPT','bobAuditCopyText'))]:
            v=Visibility();v.feed(module.PANEL)
            for key in ids:self.assertIn(key,v.hidden_ids)
            self.assertNotIn('KI-Hilfebericht kopieren',' '.join(v.visible))
        self.assertIn('bobAuditShareHint',v.visible_ids)
    def test_issue_cards_have_no_copy_action(self):
        self.assertIn('article.append(title,meta,link);',bob_problems.PANEL)
        self.assertNotIn('document.createElement(\'br\'),button,note',bob_problems.PANEL)
