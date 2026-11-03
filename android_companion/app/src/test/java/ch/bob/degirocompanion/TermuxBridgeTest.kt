package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

/** A remote command must never provide arbitrary shell text or a secret. */
class TermuxBridgeTest {
    @Test fun fixedCommandsHaveNoShellInterpreterOrSecretArguments() {
        assertEquals("com.termux", TermuxBridge.PACKAGE)
        assertEquals("com.termux.app.RunCommandService", TermuxBridge.SERVICE)
        assertEquals("/data/data/com.termux/files/usr/bin/python", TermuxBridge.PYTHON)
        val check=TermuxBridge.arguments(TermuxBridge.Action.CHECK).toList()
        val local=TermuxBridge.arguments(TermuxBridge.Action.LOCAL_ESCROW).toList()
        assertEquals(listOf(TermuxBridge.SCRIPT, "--help"), check)
        assertEquals("-c", local[0])
        assertEquals(2, local.size)
        assertTrue(local[1].contains("bob_render_to_offline_escrow.py"))
        assertTrue(local[1].contains("Signed application source integrity failed"))
        assertTrue(local[1].contains("no overwrite"))
        assertTrue(local[1].contains("os.execv"))
        assertFalse(local[1].contains("urllib.request"))
        assertFalse(local[1].contains("PUSH_SERVICE_TOKEN"))
        for (arg in check) {
            assertFalse(arg.contains("PUSH_SERVICE_TOKEN"))
            assertFalse(arg.contains("-c"))
            assertFalse(arg.contains("http"))
        }
    }

    @Test fun checkReceiptMustContainActualSuccessfulExitAndTermuxStatus() {
        assertEquals("TERMUX_CHECK_EXECUTED",
            TermuxBridge.classifyCheckResult(-1, 0))
        assertEquals("TERMUX_CHECK_FAILED",
            TermuxBridge.classifyCheckResult(-1, 2))
        assertEquals("TERMUX_INTERNAL_ERROR",
            TermuxBridge.classifyCheckResult(1, 0))
        assertEquals("TERMUX_RESULT_INCOMPLETE",
            TermuxBridge.classifyCheckResult(null, 0))
        assertEquals("TERMUX_RESULT_INCOMPLETE",
            TermuxBridge.classifyCheckResult(-1, null))
    }

    @Test fun offlineBackupCannotPickRemoteTargetOrCustomCommand() {
        assertTrue(TermuxBridge.SCRIPT.startsWith(
            "/data/data/com.termux/files/home/bob-sicher/"))
        assertTrue(TermuxBridge.OUTPUT.startsWith(
            "/data/data/com.termux/files/home/bob-sicher/"))
        assertEquals(2, TermuxBridge.Action.values().size)
    }
}
