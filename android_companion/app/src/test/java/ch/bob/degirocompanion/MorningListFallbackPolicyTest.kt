package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningListFallbackPolicyTest {
    private val pending = "a".repeat(32)
    private val previous = "b".repeat(32)
    private val plan = listOf(SelectiveDetailPlan.Entry("DE000SQ02JQ6", listOf("Hebel")))

    @Test fun memoryPollingCannotWaitForeverWithoutUsableFallback() {
        assertFalse(MorningListFallbackPolicy.pollingFinished(99,"waiting-memory",null))
        assertTrue(MorningListFallbackPolicy.pollingFinished(100,"waiting-memory",null))
        assertTrue(MorningListFallbackPolicy.pollingFinished(101,"waiting-memory",null))
        assertTrue(MorningListFallbackPolicy.pollingFinished(0,"read-failed","OCR_MEMORY_WAIT_EXHAUSTED"))
        assertFalse(MorningListFallbackPolicy.pollingFinished(0,"reading","OCR_MEMORY_WAIT_EXHAUSTED"))
        assertFalse(MorningListFallbackPolicy.pollingFinished(0,"read-failed",null))
    }

    @Test fun onlyTrueMemoryFailuresPermitSafePreviousListFallback() {
        assertTrue(MorningListFallbackPolicy.memoryDeferred("waiting-memory", null))
        assertTrue(MorningListFallbackPolicy.memoryDeferred("read-failed", "MemoryError"))
        assertFalse(MorningListFallbackPolicy.memoryDeferred("read-failed", "ListVerificationError"))
        assertFalse(MorningListFallbackPolicy.memoryDeferred("read-failed", "InterruptedWorker"))
        assertFalse(MorningListFallbackPolicy.memoryDeferred("read-failed", "MemoryError_extra"))
        assertFalse(MorningListFallbackPolicy.memoryDeferred("synced", "MemoryError"))
        assertFalse(MorningListFallbackPolicy.memoryDeferred(null, "MemoryError"))
    }

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

    @Test fun memoryOnlyResearchNeedsTerminalReceiptAndNoVerifiedPriorPlan() {
        fun ready(attempt:Int, stage:String?="read-failed", error:String?="MemoryError",
                  prior:Boolean=false) =
            MorningListFallbackPolicy.localResearchReady(attempt,stage,error,prior)
        assertFalse(ready(0))
        assertFalse(ready(5))
        assertTrue(ready(6))
        assertTrue(ready(18))
        assertTrue(ready(100))
        assertFalse(ready(101))
        assertFalse(ready(6,prior=true))
        assertFalse(ready(18,prior=true))
        assertFalse(ready(6,stage="waiting-memory",error=null))
        assertFalse(ready(17,stage="waiting-memory",error=null))
        assertTrue(ready(18,stage="waiting-memory",error=null))
        assertTrue(ready(100,stage="waiting-memory",error=null))
        assertFalse(ready(18,stage="waiting-memory",error="MemoryError"))
        assertFalse(ready(18,stage="waiting-memory",error=null,prior=true))
        assertFalse(ready(6,stage="synced"))
        assertFalse(ready(6,error="ListVerificationError"))
        assertFalse(ready(6,error=null))
    }
}
