package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class SearchClickProgressTest {
    private val label = "Mit Namen, ISIN oder Symbol suchen"
    private fun wrapper(parent: Int = -1) = MorningReadPolicy.Node("", row=label, clickAction=true, parent=parent)
    private fun tree() = listOf(wrapper(), MorningReadPolicy.Node(label,clickable=true,parent=0))
    private fun decide(nodes: List<MorningReadPolicy.Node>) = MorningReadPolicy.discoverGold(nodes)

    @Test fun acceptedClickWithoutTransitionTriesOnlyItsSearchParentOnce() {
        val p=SearchClickProgress(); val nodes=tree(); val action=decide(nodes)
        assertEquals(1,p.select(nodes,action,7,100).index)
        p.record(1,100)
        assertEquals("SEARCH_TRANSITION_PENDING",p.select(nodes,action,7,1599).code)
        val parent=p.select(nodes,action,7,1600)
        assertEquals(0,parent.index); assertEquals("SEARCH_RETRY_PARENT",parent.code)
        // Observation alone never consumes a click.
        assertEquals(parent,p.select(nodes,action,7,1700))
        p.record(0,1700)
        assertEquals("SEARCH_NO_PROGRESS",p.select(nodes,action,7,3200).code)
        assertEquals("SEARCH_NO_PROGRESS",p.select(nodes,action,7,90000).code)
    }
    @Test fun unchangedSingleSearchDoesNotRepeatOrUseToolbarSibling() {
        val nodes=listOf(MorningReadPolicy.Node(label,clickable=true),MorningReadPolicy.Node("Suchen",clickable=true))
        val p=SearchClickProgress();val action=decide(nodes)
        assertEquals(0,p.select(nodes,action,1,0).index);p.record(0,0)
        assertEquals("SEARCH_NO_PROGRESS",p.select(nodes,action,1,2000).code)
    }
    @Test fun aggregateDisabledSensitiveAndInputParentsCannotBeClicked() {
        for(parent in listOf(wrapper().copy(row=label+"\nPortfolio"),wrapper().copy(enabled=false),
            wrapper().copy(sensitive=true),wrapper().copy(password=true),wrapper().copy(containsInput=true),
            wrapper().copy(description="Order platzieren"))) {
            val nodes=listOf(parent,tree()[1])
            val action=MorningReadPolicy.Action(MorningReadPolicy.Kind.SEARCH,1)
            assertEquals(listOf(1),MorningReadPolicy.searchClickChain(nodes,action))
        }
    }
    @Test fun inputTransitionClearsRetryAndPreservesNormalQuery() {
        val p=SearchClickProgress();val nodes=tree();val action=decide(nodes)
        p.select(nodes,action,1,0);p.record(1,0)
        val inputs=listOf(MorningReadPolicy.Node("",editable=true,hint=label))
        val query=p.select(inputs,decide(inputs),1,2000)
        assertEquals(MorningReadPolicy.Kind.QUERY,query.kind)
        assertEquals(1,p.select(nodes,action,1,4000).index)
    }
    @Test fun orderAndLoginProtectionWinsBeforeAnyRetry() {
        for(text in listOf("Passwort","Order bestätigen","Limitpreis","Anmelden")) {
            val p=SearchClickProgress();val nodes=tree();p.select(nodes,decide(nodes),1,0);p.record(1,0)
            val protected=nodes+MorningReadPolicy.Node(text)
            assertEquals(MorningReadPolicy.Kind.BLOCK,p.select(protected,decide(protected),1,2000).kind)
        }
    }
    @Test fun isolatedMarketOrderLauncherDoesNotBecomeFallback() {
        val nodes=tree()+listOf(MorningReadPolicy.Node("Märkte"),MorningReadPolicy.Node("Indizes"),
            MorningReadPolicy.Node("",description="Order platzieren",clickable=true))
        val p=SearchClickProgress();val action=decide(nodes)
        assertEquals(1,p.select(nodes,action,1,0).index);p.record(1,0)
        assertEquals(0,p.select(nodes,action,1,2000).index);p.record(0,2000)
        assertEquals("SEARCH_NO_PROGRESS",p.select(nodes,action,1,4000).code)
    }
    @Test fun resetWindowChangeAndNewTargetDiscardOldRetryState() {
        val p=SearchClickProgress();val nodes=tree();val action=decide(nodes)
        p.select(nodes,action,1,0);p.record(1,0)
        assertEquals(1,p.select(nodes,action,2,2000).index)
        p.record(1,2000);p.clear()
        assertEquals(1,p.select(nodes,action,2,4000).index)
        val changed=listOf(MorningReadPolicy.Node("Suchen",clickable=true))
        assertEquals(0,p.select(changed,decide(changed),2,6000).index)
    }
    @Test fun chainIsBoundedAndCyclesStop() {
        val nodes=listOf(wrapper(),wrapper(0),wrapper(1),wrapper(2),MorningReadPolicy.Node(label,clickable=true,parent=3))
        assertEquals(listOf(4,3,2),MorningReadPolicy.searchClickChain(nodes,decide(nodes)))
        val cyclic=listOf(wrapper(1),MorningReadPolicy.Node(label,clickable=true,parent=0))
        assertEquals(listOf(1,0),MorningReadPolicy.searchClickChain(cyclic,MorningReadPolicy.Action(MorningReadPolicy.Kind.SEARCH,1)))
    }
}
