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
        assertNull(decision(ids=local.take(8)))
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
}
