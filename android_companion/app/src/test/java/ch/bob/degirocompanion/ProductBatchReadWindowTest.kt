package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductBatchReadWindowTest {
    private val isin="DE000FB0CVV9"
    private val draft="BOB APP-LESEENTWURF – NICHT VERIFIZIERT\nISIN: $isin\nGeld (Anzeige ungeprüft): 19,46"
    private fun keep(previous:Boolean=false,current:Boolean=false,finished:Boolean=false,
                     text:String=draft,expected:String=isin,sensitive:Boolean=false,
                     unsafe:Boolean=false)=ProductBatchReadWindow.keep(
        previous,current,finished,text,expected,sensitive,unsafe)
    @Test fun finishedExactProductKeepsWindowAfterReaderResetsAnchor() {
        assertTrue(keep(finished=true))
        assertTrue(keep(previous=true))
        assertTrue(keep(current=true))
    }
    @Test fun neverKeepUnidentifiedOrProtectedTransition() {
        assertFalse(keep(finished=true,text=""))
        assertFalse(keep(finished=true,text=draft.replace(isin,"DE000SQ02JQ6")))
        assertFalse(keep(finished=false))
        assertFalse(keep(finished=true,sensitive=true))
        assertFalse(keep(finished=true,unsafe=true))
        assertFalse(keep(previous=true,sensitive=true))
        assertFalse(keep(current=true,unsafe=true))
        assertFalse(keep(finished=true,expected="WRONG"))
    }
}
