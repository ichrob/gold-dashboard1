package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningListResumePolicyTest {
    private val policy=MorningListResumePolicy
    private val minute=60_000L

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
