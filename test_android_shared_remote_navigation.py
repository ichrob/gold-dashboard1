"""Integration boundaries for reusing the morning reader's guarded gestures."""
from pathlib import Path
import unittest
S=Path('android_companion/app/src/main/java/ch/bob/degirocompanion/ProductReadService.kt').read_text()
class SharedRemoteNavigationTests(unittest.TestCase):
    def test_remote_uses_existing_gesture_engine_only_after_explicit_command(self):
        start=S.index('if(command==null || actionName=="inspect")return result')
        end=S.index('private fun tapRecognizedSearch',start)
        remote=S[start:end]
        self.assertIn('remoteGestureBudget.take(commandSession,root.windowId,kind,query)',remote)
        self.assertIn('tapRecognizedSearch(root.windowId,input,category,product,query,commandSession)',remote)
        for route in ('RESULT -> tap(product=true)','CATEGORY -> tap(category=true)','FOCUS -> tap(input=true)'):
            self.assertIn(route,remote)
        self.assertIn('if(decision.code!="SEARCH_NO_PROGRESS") return result',remote)
        self.assertNotIn('GoldSearchRun.start',remote)
    def test_shared_engine_retains_safety_and_session_revalidation(self):
        body=S.split('private fun tapRecognizedSearch',1)[1].split('private fun keyboardVisible',1)[0]
        for gate in ('remoteSession == PhoneRemote.sessionId()', '!MorningReadRun.running && !GoldSearchRun.running',
                     'magnificationController.scale != 1f','root.windowId!=expectedWindow',
                     'MorningReadPolicy.resultTapIndex','target.isPassword',
                     'if(refreshed!=bounds || !authorized()) return false'):
            self.assertIn(gate,body)
        self.assertIn('ProductReadRequest.active(SystemClock.elapsedRealtime())',body)
