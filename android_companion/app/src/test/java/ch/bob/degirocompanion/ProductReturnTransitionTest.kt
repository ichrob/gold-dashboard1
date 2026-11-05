package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductReturnTransitionTest {
    private val isin="DE000FD0S0G4"
    private val oldPage=listOf("Übersicht","Kursdaten","Geld EUR 10,20","Brief EUR 10,30",isin)
        .map { MorningReadPolicy.Node(it) } + MorningReadPolicy.Node("Order platzieren",clickable=true)
    private val search=listOf(
        MorningReadPolicy.Node("Märkte"),
        MorningReadPolicy.Node("Nach Produkttyp durchsuchen"),
        MorningReadPolicy.Node("",id="product-search",editable=true,focused=true)
    )
    private fun poll(nodes:List<MorningReadPolicy.Node>,time:Long=1100,window:Int=7):
        ProductReturnTransition.State {
        val t=ProductReturnTransition()
        t.begin(isin,7,1000)
        return t.poll(nodes,window,time)
    }

    @Test fun alreadyReturnedSearchCanContinueWithoutAnotherBack() {
        val recent=search + listOf("Zuletzt", "Alle löschen", "DE000SX7PE82", "DE000FG9NLJ8")
            .map { MorningReadPolicy.Node(it) }
        val t=ProductReturnTransition()
        assertTrue(t.confirmSearch(recent,isin,7,1000))
        assertEquals(ProductReturnTransition.State.IDLE,t.poll(oldPage,7,1001))
        assertFalse(t.confirmSearch(oldPage,isin,7,1000))
        for (bad in listOf(MorningReadPolicy.Node("Order bestätigen"),
            MorningReadPolicy.Node("Passwort"),MorningReadPolicy.Node("",sensitive=true),
            MorningReadPolicy.Node("",id="order-quantity",editable=true)))
            assertFalse(t.confirmSearch(recent+bad,isin,7,1000))
    }

    @Test fun boundedSecondBackRequiresSameVisibleProductAndSafeReadOnlyPage() {
        val t=ProductReturnTransition()
        t.begin(isin,7,1000)
        assertEquals(ProductReturnTransition.State.WAITING,t.poll(oldPage,7,1200))
        assertFalse(t.safeBackRetry(oldPage,7,1800))
        assertTrue(t.safeBackRetry(oldPage,7,2400))
        assertFalse(t.safeBackRetry(oldPage,7,3700))
        assertEquals(ProductReturnTransition.State.WAITING,t.poll(oldPage,7,4300))
        assertEquals(ProductReturnTransition.State.FAILED,t.poll(oldPage,7,7400))
    }

    @Test fun retryNeverActsOnOtherIsinWindowOrderOrSearch() {
        fun allowed(nodes:List<MorningReadPolicy.Node>,window:Int=7):Boolean {
            val t=ProductReturnTransition();t.begin(isin,7,1000)
            t.poll(nodes,window,2400)
            return t.safeBackRetry(nodes,window,2400)
        }
        assertFalse(allowed(search))
        assertFalse(allowed(oldPage,8))
        assertFalse(allowed(oldPage+MorningReadPolicy.Node("DE000FE2JJ20")))
        assertFalse(allowed(oldPage+MorningReadPolicy.Node("Order bestätigen")))
        assertFalse(allowed(oldPage+MorningReadPolicy.Node("Passwort")))
        assertFalse(allowed(oldPage+MorningReadPolicy.Node("",editable=true)))
        assertFalse(allowed(oldPage.filterNot { it.text==isin }))
    }

    @Test fun previousProductIsNeverPassedToNextTargetEvenOnTimeout() {
        val t=ProductReturnTransition()
        assertEquals(ProductReturnTransition.State.IDLE,t.poll(oldPage,7,1000))
        t.begin(isin,7,1000)
        assertEquals(ProductReturnTransition.State.WAITING,t.poll(oldPage,7,1001))
        assertEquals(ProductReturnTransition.State.WAITING,t.poll(oldPage,7,5999))
        assertEquals(ProductReturnTransition.State.FAILED,t.poll(oldPage,7,6000))
        assertEquals(ProductReturnTransition.State.IDLE,t.poll(oldPage,7,6001))
    }
    @Test fun onlyVerifiedMarketsSearchReleasesNextProduct() {
        val t=ProductReturnTransition();t.begin(isin,7,1000)
        assertEquals(ProductReturnTransition.State.WAITING,t.poll(oldPage,7,1100))
        assertEquals(ProductReturnTransition.State.READY,t.poll(search,7,1200))
        assertEquals(ProductReturnTransition.State.IDLE,t.poll(oldPage,7,1300))
    }
    @Test fun genericSearchInputWithoutMarketsEvidenceNeverReleases() {
        assertEquals(ProductReturnTransition.State.FAILED,poll(
            listOf(MorningReadPolicy.Node("",id="product-search",editable=true))))
        assertEquals(ProductReturnTransition.State.FAILED,poll(
            search+MorningReadPolicy.Node("",id="order-quantity",editable=true)))
    }
    @Test fun globalOrderLauncherBesideVerifiedSearchIsNotAnOrderForm() {
        val isolated=search+MorningReadPolicy.Node("Order platzieren",clickable=true)
        assertEquals(ProductReturnTransition.State.READY,poll(isolated))
    }
    @Test fun oldOverviewRemainsPassiveUntilSearchOrFailClosed() {
        val old=listOf(MorningReadPolicy.Node("Übersicht"),
            MorningReadPolicy.Node(isin),
            MorningReadPolicy.Node("Order platzieren",clickable=true))
        assertEquals(ProductReturnTransition.State.WAITING,poll(old,2399))
        assertEquals(ProductReturnTransition.State.WAITING,poll(old,2400))
        assertEquals(ProductReturnTransition.State.FAILED,poll(old,6000))
    }
    @Test fun realOrderFormsAndChangedIdentityAlwaysFailClosed() {
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),
            MorningReadPolicy.Node("Limitpreis"),MorningReadPolicy.Node("Passwort"),
            MorningReadPolicy.Node("",editable=true),MorningReadPolicy.Node("",sensitive=true),
            MorningReadPolicy.Node("DE000FE2JJ20"))) {
            assertEquals(ProductReturnTransition.State.FAILED,poll(oldPage+extra))
        }
    }
    @Test fun searchWithOrderConfirmationIsNeverAccepted() {
        val form=search + MorningReadPolicy.Node("Order bestätigen")
        assertEquals(ProductReturnTransition.State.FAILED,poll(form))
        assertEquals(ProductReturnTransition.State.FAILED,poll(
            search+MorningReadPolicy.Node("Limitpreis")))
    }
    @Test fun unknownWindowCannotBeTreatedAsSearchWithoutEvidence() {
        assertEquals(ProductReturnTransition.State.FAILED,poll(oldPage,1100,8))
        assertEquals(ProductReturnTransition.State.FAILED,poll(oldPage,999))
        // Window IDs are not proof; a verified Markets search has its own
        // independent content validation.
        assertEquals(ProductReturnTransition.State.READY,poll(search,1100,8))
    }
}
