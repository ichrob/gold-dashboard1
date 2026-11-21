package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningListResumePolicyTest {
    private val policy=MorningListResumePolicy
    private val minute=60_000L

    @Test fun rejectedListDoesNotMonopolizeAnotherExplicitStart() {
        assertTrue(policy.verificationFailed("read-failed","ListVerificationError"))
        for(age in listOf(0L, 3*minute, 60*minute))
            for(resumes in 0..3)
                assertEquals(MorningListResumePolicy.Mode.NEW_LIST,
                    policy.mode(age,resumes,verificationFailed=true))
    }

    @Test fun missingSavedReceiptCannotHoldFreshOwnerStartIndefinitely() {
        assertFalse(policy.receiptUnavailableForFreshCapture(2,true,false,null))
        assertTrue(policy.receiptUnavailableForFreshCapture(3,true,false,null))
        assertTrue(policy.receiptUnavailableForFreshCapture(3,true,true,""))
        assertTrue(policy.receiptUnavailableForFreshCapture(3,true,true,"missing"))
        assertTrue(policy.receiptUnavailableForFreshCapture(4,true,true,"not-found"))
        assertFalse(policy.receiptUnavailableForFreshCapture(100,false,false,null))
        for(stage in listOf("reading","waiting-memory","read-failed",
            "synced","superseded"))
            assertFalse(policy.receiptUnavailableForFreshCapture(100,true,true,stage))
        assertEquals(MorningListResumePolicy.Mode.NEW_LIST,
            policy.mode(15*minute,1,receiptUnconfirmed=true))
        assertEquals(MorningListResumePolicy.Mode.NEW_LIST,
            policy.mode(120*minute,0,receiptUnconfirmed=true))
        // Valid previous receipts are never treated as missing, regardless
        // of how many HTTP status checks have elapsed.
        assertFalse(policy.receiptUnavailableForFreshCapture(100,true,true,"reading"))
    }

    @Test fun unknownTransportAndMemoryStatesAreNotRejectedLists() {
        for(stage in listOf(null,"reading","waiting-memory","synced","superseded"))
            assertFalse(policy.verificationFailed(stage,"ListVerificationError"))
        for(error in listOf(null,"MemoryError","InterruptedWorker","ConnectionError"))
            assertFalse(policy.verificationFailed("read-failed",error))
        assertEquals(MorningListResumePolicy.Mode.RETRY_TRANSFER,
            policy.mode(0,0,verificationFailed=false))
    }

    @Test fun onlyTerminalEnhancedFailureMayStartFreshCaptureInSameSession() {
        assertTrue(policy.terminalVerificationFailed("read-failed","ListVerificationError",true))
        assertFalse(policy.terminalVerificationFailed("read-failed","ListVerificationError",false))
        for(stage in listOf(null,"reading","waiting-memory","synced","superseded"))
            assertFalse(policy.terminalVerificationFailed(stage,"ListVerificationError",true))
        for(error in listOf(null,"MemoryError","InterruptedWorker","ConnectionError"))
            assertFalse(policy.terminalVerificationFailed("read-failed",error,true))
        assertEquals(MorningListResumePolicy.Mode.NEW_LIST,
            policy.mode(96*minute,0,verificationFailed=true))
    }

    @Test fun recentUnfinishedBatchCanRetryOriginalUploadOnlyWithinBoundedAttempts() {
        assertEquals(MorningListResumePolicy.Mode.RETRY_TRANSFER,policy.mode(0,0))
        assertEquals(MorningListResumePolicy.Mode.RETRY_TRANSFER,policy.mode(14*minute,1))
        assertEquals(MorningListResumePolicy.Mode.RETRY_TRANSFER,policy.mode(15*minute,0))
        assertEquals(MorningListResumePolicy.Mode.CHECK_RECEIPT_ONLY,policy.mode(15*minute,2))
    }

    @Test fun lateServerConfirmationIsStatusOnlyAndDoesNotReuploadPrivateImages() {
        assertEquals(MorningListResumePolicy.Mode.CHECK_RECEIPT_ONLY,policy.mode(16*minute,0))
        assertEquals(MorningListResumePolicy.Mode.CHECK_RECEIPT_ONLY,policy.mode(80*minute,1))
        assertEquals(MorningListResumePolicy.Mode.CHECK_RECEIPT_ONLY,policy.mode(179*minute,2))
        assertEquals(MorningListResumePolicy.Mode.CHECK_RECEIPT_ONLY,policy.mode(180*minute,0))
        assertEquals(MorningListResumePolicy.Mode.NEW_LIST,policy.mode(181*minute,0))
    }

    @Test fun expiredAndOverretriedBatchesNeverHijackNewUserStart() {
        for(age in listOf(-1L,181*minute,24*60*minute,24*60*minute+1))
            assertEquals(MorningListResumePolicy.Mode.NEW_LIST,policy.mode(age,3))
        assertEquals(MorningListResumePolicy.Mode.NEW_LIST,policy.mode(-1L,0))
        assertEquals(MorningListResumePolicy.Mode.NEW_LIST,policy.mode(3*minute,4))
        assertEquals(MorningListResumePolicy.Mode.NEW_LIST,policy.mode(3*minute,-1))
        assertEquals(MorningListResumePolicy.Mode.NEW_LIST,policy.mode(60*minute,3))
    }
}
