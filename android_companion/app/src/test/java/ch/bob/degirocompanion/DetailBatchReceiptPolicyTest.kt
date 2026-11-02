package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class DetailBatchReceiptPolicyTest {
    private val batch="a".repeat(32)
    private fun check(returned:String=batch,stage:String?="synced") =
        DetailBatchReceiptPolicy.decide(batch,returned,stage)

    @Test fun onlyAnOwnedConfirmedOriginalListCanAuthorizeUpload() {
        assertEquals(DetailBatchReceiptPolicy.Decision.UPLOAD,check())
        assertEquals(DetailBatchReceiptPolicy.Decision.UPLOAD,check(stage="superseded"))
        assertEquals(DetailBatchReceiptPolicy.Decision.DEFER_UNAVAILABLE,check(stage=null))
    }
    @Test fun unrelatedOrUnfinishedBatchCanNeverAuthorizeUpload() {
        assertEquals(DetailBatchReceiptPolicy.Decision.RETRY_LATER,check(returned="b".repeat(32)))
        for(stage in listOf("fetching","waiting-memory","reading","read-failed","store-failed","invalid","")) {
            assertEquals(stage,DetailBatchReceiptPolicy.Decision.RETRY_LATER,check(stage=stage))
        }
        assertEquals(DetailBatchReceiptPolicy.Decision.RETRY_LATER,
            DetailBatchReceiptPolicy.decide("not-a-batch",batch,"synced"))
    }
    @Test fun absentBatchNeverBecomesNewListEvidence() {
        assertEquals(DetailBatchReceiptPolicy.Decision.DEFER_UNAVAILABLE,check(stage=null))
        // A remote batch from a different key cannot be substituted for the
        // original even if its own import status is 'synced'.
        assertEquals(DetailBatchReceiptPolicy.Decision.RETRY_LATER,check(returned="c".repeat(32),stage="synced"))
    }
}
