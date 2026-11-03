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
        assertEquals(listOf(TermuxBridge.SCRIPT, "create", "--output", TermuxBridge.OUTPUT), local)
        for (arg in check+local) {
            assertFalse(arg.contains("PUSH_SERVICE_TOKEN"))
            assertFalse(arg.contains("BOB_ARCHIVE_RECOVERY_ROOT_TOKEN"))
            assertFalse(arg.contains("-c"))
            assertFalse(arg.contains("http"))
        }
    }

    @Test fun offlineBackupCannotPickRemoteTargetOrCustomCommand() {
        assertTrue(TermuxBridge.SCRIPT.startsWith(
            "/data/data/com.termux/files/home/bob-sicher/"))
        assertTrue(TermuxBridge.OUTPUT.startsWith(
            "/data/data/com.termux/files/home/bob-sicher/"))
        assertEquals(2, TermuxBridge.Action.values().size)
    }
}
