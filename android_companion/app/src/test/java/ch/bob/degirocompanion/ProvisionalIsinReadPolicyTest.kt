package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProvisionalIsinReadPolicyTest {
    private fun valid(n:Int):String {
        val prefix="DE000ZX"+n.toString().padStart(4,'0')
        return ('0'..'9').map { prefix+it }
            .single { SeriesEvidence.validIsin(it) }
    }
    private val local=(1..10).map(::valid)
    private fun decision(
        ids:List<String> = local,
        same:Boolean=true,
        stage:String="read-failed",
        error:String="ListVerificationError",
        enhanced:Boolean=true,
        recognized:Int=9,
        expected:Int=10,
        images:Int=3,
        conflicts:Int=0
    )=ProvisionalIsinReadPolicy.candidates(
        ids,same,stage,error,enhanced,recognized,expected,images,conflicts)

    @Test fun nineOfTenSupportsOnlyLocalResearchNotListValidation() {
        assertEquals(local,decision())
        assertEquals(local.take(9),decision(ids=local.take(9)))
        assertEquals(local,decision(images=4))
        assertNotSame(local,decision())
    }

    @Test fun noFakeProductsOrImplicitFallbackOnOtherFailures() {
        // Android virtualizes list rows. Server may see nine complete rows
        // even when its accessibility tree exposed fewer candidate identities.
        // Only genuinely seen, unique ISINs may be locally researched.
        assertEquals(local.take(8),decision(ids=local.take(8)))
        assertEquals(local.take(1),decision(ids=local.take(1)))
        assertNull(decision(ids=emptyList()))
        assertNull(decision(ids=local+local.first()))
        assertNull(decision(ids=local.dropLast(1)+local[0]))
        assertNull(decision(ids=local.dropLast(1)+"INVALID"))
        assertNull(decision(same=false))
        assertNull(decision(stage="reading"))
        assertNull(decision(stage="synced"))
        assertNull(decision(error="OCR_MEMORY_WAIT_EXHAUSTED"))
        assertNull(decision(enhanced=false))
        assertNull(decision(recognized=8))
        assertNull(decision(recognized=10))
        assertNull(decision(expected=9))
        assertNull(decision(images=2))
        assertNull(decision(images=5))
        assertNull(decision(conflicts=1))
    }

    @Test fun memoryExhaustionAllowsOnlyFreshBatchTenLocallyObservedIdentityReads() {
        val batch="a".repeat(32)
        fun memory(
            ids: List<String> = local,
            receiptBatch: String = batch,
            stage: String = "read-failed",
            error: String = "MemoryError",
            images: Int = 3,
            resumed: Boolean = false
        ) = ProvisionalIsinReadPolicy.memoryCandidates(
            ids,batch,receiptBatch,stage,error,images,resumed)
        assertEquals(local,memory())
        assertNotSame(local,memory())
        assertEquals(local,memory(images=4))
        assertNull(memory(ids=local.take(9)))
        assertNull(memory(ids=local.dropLast(1)+local.first()))
        assertNull(memory(ids=local.dropLast(1)+"INVALID"))
        assertNull(memory(receiptBatch="b".repeat(32)))
        assertNull(memory(stage="waiting-memory"))
        assertEquals(local,memory(stage="waiting-memory",error=""))
        assertNull(memory(stage="waiting-memory",error="MemoryError"))
        assertNull(memory(stage="synced"))
        assertNull(memory(error="ListVerificationError"))
        assertNull(memory(error="OCR_MEMORY_WAIT_EXHAUSTED"))
        assertNull(memory(images=2))
        assertNull(memory(images=5))
        assertNull(memory(resumed=true))
        assertNull(ProvisionalIsinReadPolicy.memoryCandidates(
            local,"invalid",batch,"read-failed","MemoryError",3,false))
    }
}
