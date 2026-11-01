package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningReadRetryPolicyTest {
    @Test fun preservesPartialObservationWhenOnlyLeverageUnavailable() {
        assertFalse(MorningReadRetryPolicy.retry("PARTIAL",true,listOf("Hebel"),1))
        assertFalse(MorningReadRetryPolicy.retry("PARTIAL",true,listOf("Hebel"),2))
    }
    @Test fun retriesMissingQuoteOrFirstFailedAttemptOnce() {
        assertTrue(MorningReadRetryPolicy.retry("PARTIAL",true,listOf("Brief","Hebel"),1))
        assertTrue(MorningReadRetryPolicy.retry("RESULT_MISSING",false,
            listOf("Geld","Brief","Anzeigezeit","Hebel"),1))
        assertTrue(MorningReadRetryPolicy.retry("RETURN_FAILED",false,
            listOf("Geld"),1))
        assertFalse(MorningReadRetryPolicy.retry("RETURN_FAILED",false,
            listOf("Geld"),2))
        assertFalse(MorningReadRetryPolicy.retry("COMPLETE",true,emptyList(),1))
    }
}
