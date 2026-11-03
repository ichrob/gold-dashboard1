package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningListFallbackPolicyTest {
    private val pending = "a".repeat(32)
    private val previous = "b".repeat(32)
    private val plan = listOf(SelectiveDetailPlan.Entry("DE000SQ02JQ6", listOf("Hebel")))

    @Test fun onlyBoundedOlderBatchCanSupplyMissingFieldPlan() {
        assertTrue(MorningListFallbackPolicy.allowed(18, pending, previous, plan))
        assertTrue(MorningListFallbackPolicy.allowed(100, pending, previous, plan))
        assertFalse(MorningListFallbackPolicy.allowed(17, pending, previous, plan))
        assertFalse(MorningListFallbackPolicy.allowed(0, pending, previous, plan))
        assertTrue(MorningListFallbackPolicy.allowed(0, pending, previous, plan, resumedSavedCapture = true))
        assertTrue(MorningListFallbackPolicy.allowed(17, pending, previous, plan, resumedSavedCapture = true))
        assertFalse(MorningListFallbackPolicy.allowed(101, pending, previous, plan, resumedSavedCapture = true))
        assertFalse(MorningListFallbackPolicy.allowed(0, pending, pending, plan, resumedSavedCapture = true))
        assertFalse(MorningListFallbackPolicy.allowed(0, pending, previous, null, resumedSavedCapture = true))
        assertFalse(MorningListFallbackPolicy.allowed(0, pending, previous, plan + plan, resumedSavedCapture = true))
        assertFalse(MorningListFallbackPolicy.allowed(101, pending, previous, plan))
        assertFalse(MorningListFallbackPolicy.allowed(18, pending, pending, plan))
        assertFalse(MorningListFallbackPolicy.allowed(18, pending, "invalid", plan))
        assertFalse(MorningListFallbackPolicy.allowed(18, pending, previous, null))
        assertFalse(MorningListFallbackPolicy.allowed(18, pending, previous, emptyList()))
        assertFalse(MorningListFallbackPolicy.allowed(18, pending, previous, plan + plan))
    }
}
