package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class PostLoginRootRetryPolicyTest {
    @Test fun absentRootRetriesAreBounded() {
        for (attempt in 0..4) assertTrue(PostLoginRootRetryPolicy.canRetry(attempt))
        for (attempt in listOf(-1,5,6,100)) assertFalse(PostLoginRootRetryPolicy.canRetry(attempt))
    }

    @Test fun newFailureCodesRemainDiagnosticAndHumanReadable() {
        for(code in listOf("LOGIN_HANDOFF_NO_ROOT","LOGIN_HANDOFF_OTHER_APP",
                "LOGIN_HANDOFF_START_FAILED","LOGIN_HANDOFF_DISABLED")) {
            assertEquals(code,PhoneDiagnosticPolicy.code(code))
            assertFalse(MorningReadUiPolicy.reason(code).contains("($code)"))
        }
    }
}
