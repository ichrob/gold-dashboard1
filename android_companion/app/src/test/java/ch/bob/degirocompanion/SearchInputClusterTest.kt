package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class SearchInputClusterTest {
    private val wrapper=MorningReadPolicy.Node("")
    private val input=MorningReadPolicy.Node("",editable=true,parent=0)
    private val label=MorningReadPolicy.Node("Mit Namen, ISIN oder Symbol suchen",parent=0)
    @Test fun associatesOnlySmallIsolatedPromptAndInput() {
        assertEquals(setOf(1),SearchInputCluster.identify(listOf(wrapper,input,label)))
        for(extra in listOf(MorningReadPolicy.Node("Limitpreis",parent=0),
                MorningReadPolicy.Node("Order bestätigen",parent=0),
                input, input.copy(password=true), input.copy(sensitive=true)))
            assertTrue(SearchInputCluster.identify(listOf(wrapper,input,label,extra)).isEmpty())
        assertTrue(SearchInputCluster.identify(listOf(wrapper,input,label.copy(parent=-1))).isEmpty())
        assertTrue(SearchInputCluster.identify(listOf(wrapper,input.copy(hint="Betrag"),label)).isEmpty())
        assertTrue(SearchInputCluster.identify(listOf(wrapper,input,label.copy(text="Suche"))).isEmpty())
    }
    @Test fun focusPrecedesQueryAndSubmitButNeverOverridesOrderGuard() {
        val n=input.copy(hint=label.text,focused=false,focusAction=true)
        assertEquals(MorningReadPolicy.Kind.FOCUS,MorningReadPolicy.discoverGold(listOf(n)).kind)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(n.copy(focused=true))).kind)
        assertEquals(MorningReadPolicy.Kind.SUBMIT,MorningReadPolicy.discoverGold(listOf(n.copy(focused=true,text="Gold",imeEnter=true))).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(n,MorningReadPolicy.Node("Limitpreis"))).kind)
    }
}
