package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductReturnTransitionTest {
    private val isin="DE000FD0S0G4"
    private val oldPage=listOf("Übersicht","Kursdaten","Geld EUR 10,20","Brief EUR 10,30",isin)
        .map { MorningReadPolicy.Node(it) } + MorningReadPolicy.Node("Order platzieren",clickable=true)
    @Test fun oldPageWaitsWithoutBeingValidatedAgainstTheNextTarget() {
        val t=ProductReturnTransition()
        assertFalse(t.waiting(oldPage,7,1000))
        t.begin(isin,7,1000)
        assertTrue(t.waiting(oldPage,7,1001))
        assertTrue(t.waiting(oldPage,7,5999))
        assertFalse(t.waiting(oldPage,7,6000))
        assertFalse(t.waiting(oldPage,7,6001))
    }
    @Test fun arrivingSearchEndsTransitionPermanently() {
        val t=ProductReturnTransition();t.begin(isin,7,1000)
        assertTrue(t.waiting(oldPage,7,1100))
        val search=listOf(MorningReadPolicy.Node("Mit Namen, ISIN oder Symbol suchen",editable=true))
        assertFalse(t.waiting(search,7,1200))
        assertFalse(t.waiting(oldPage,7,1300))
    }
    @Test fun protectedOrChangedViewsAreNeverHiddenByWaiting() {
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("Passwort"),MorningReadPolicy.Node("",sensitive=true),
            MorningReadPolicy.Node("",editable=true),MorningReadPolicy.Node("DE000FE2JJ20"))) {
            val t=ProductReturnTransition();t.begin(isin,7,1000)
            assertFalse(t.waiting(oldPage+extra,7,1100))
        }
        for(now in listOf(999L,6000L)) {
            val t=ProductReturnTransition();t.begin(isin,7,1000)
            assertFalse(t.waiting(oldPage,7,now))
        }
        val t=ProductReturnTransition();t.begin(isin,7,1000)
        assertFalse(t.waiting(oldPage,8,1100))
    }
}
