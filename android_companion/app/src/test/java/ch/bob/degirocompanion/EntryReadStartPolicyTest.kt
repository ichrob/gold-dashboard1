package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class EntryReadStartPolicyTest {
    @Test fun idleSessionDoesNotBlockOwnerRequestedLogin() {
        assertTrue(EntryReadStartPolicy.mayReplaceIdleSession(false,false,false,false,false))
    }
    @Test fun everyRunningWorkflowRemainsProtected() {
        for(mask in 1..31) {
            assertFalse(EntryReadStartPolicy.mayReplaceIdleSession(
                mask and 1 != 0, mask and 2 != 0, mask and 4 != 0,
                mask and 8 != 0, mask and 16 != 0))
        }
    }
    @Test fun allStartFailuresSurviveAndroidSanitizer() {
        for(code in EntryReadStartPolicy.Code.values())
            assertEquals(code.name,PhoneDiagnosticPolicy.code(code.name))
        assertEquals("OTHER",PhoneDiagnosticPolicy.code("arbitrary private text"))
    }
}
