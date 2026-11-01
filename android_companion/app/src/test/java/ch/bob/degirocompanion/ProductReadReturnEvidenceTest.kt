package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class ProductReadReturnEvidenceTest {
    private val isin="DE000FB0CVV9"
    private val draft=ProductScreenEvidence.HEADER+"\nISIN: "+isin
    private val step=ProductPageReader.Step(ProductPageReader.Move.FINISHED,
        ProductScreenEvidence.Result(draft=draft,message=""))
    @Test fun directFinishRetainsExactIdentity() {
        assertTrue(ProductReadReturnEvidence.confirmed(false,false,step,setOf(isin),isin,false))
    }
    @Test fun refusesWrongOrAbsentIdentity() {
        for(ids in listOf(emptySet<String>(),setOf("DE000FE6B3G9"),
            setOf(isin,"DE000FE6B3G9")))
            assertFalse(ProductReadReturnEvidence.confirmed(false,false,step,ids,isin,false))
        assertFalse(ProductReadReturnEvidence.confirmed(false,false,step,setOf(isin),isin,true))
        assertFalse(ProductReadReturnEvidence.confirmed(false,false,step,setOf(isin),
            "DE000FE6B3G9",false))
    }
}
