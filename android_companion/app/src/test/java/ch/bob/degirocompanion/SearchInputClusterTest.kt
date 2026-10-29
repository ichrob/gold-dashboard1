package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class SearchInputClusterTest {
    @Test fun spatialPromptRequiresContainmentAndOneSmallVisibleInput() {
        val screen=SearchInputCluster.Box(0,0,700,1500)
        val field=SearchInputCluster.Box(24,200,680,290)
        val prompt=SearchInputCluster.Box(100,220,600,270)
        val nodes=listOf(MorningReadPolicy.Node("",editable=true,id="generic-input"),
            MorningReadPolicy.Node("Mit Namen, ISIN oder Symbol suchen"))
        assertEquals(setOf(0),SearchInputCluster.spatial(nodes,listOf(field,prompt),screen))
        assertTrue(SearchInputCluster.spatial(nodes,listOf(field,prompt.copy(top=300,bottom=330)),screen).isEmpty())
        assertTrue(SearchInputCluster.spatial(nodes,listOf(screen,prompt),screen).isEmpty())
        assertTrue(SearchInputCluster.spatial(nodes+nodes[0],listOf(field,prompt,field),screen).isEmpty())
        for(n in listOf(nodes[0].copy(password=true),nodes[0].copy(sensitive=true),nodes[0].copy(enabled=false)))
            assertTrue(SearchInputCluster.spatial(listOf(n,nodes[1]),listOf(field,prompt),screen).isEmpty())
        // Inferred identity must not erase a conflicting form label.
        val marked=nodes[0].copy(id="bob:search_input",hint="Limitpreis")
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(marked,nodes[1])).kind)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(marked.copy(hint=""),nodes[1])).kind)
        assertEquals(MorningReadPolicy.Kind.SUBMIT,MorningReadPolicy.discoverGold(listOf(marked.copy(hint="",text="Gold",imeEnter=true))).kind)
    }
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
        assertEquals(MorningReadPolicy.Kind.FOCUS,MorningReadPolicy.discoverGold(listOf(n.copy(focusAction=false))).kind)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(n.copy(focused=true))).kind)
        assertEquals(MorningReadPolicy.Kind.SUBMIT,MorningReadPolicy.discoverGold(listOf(n.copy(focused=true,text="Gold",imeEnter=true))).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(n,MorningReadPolicy.Node("Limitpreis"))).kind)
    }
    @Test fun nestedPlaceholderSupportsSecondTapThenTextThenSubmit() {
        val field=input.copy(parent=-1,focused=false)
        val child=label.copy(parent=0)
        val tree=listOf(field,child)
        val matched=SearchInputCluster.spatial(tree,listOf(SearchInputCluster.Box(20,200,680,290),
            SearchInputCluster.Box(100,220,600,270)),SearchInputCluster.Box(0,0,700,1500))
        assertEquals(setOf(0),matched)
        val identified=field.copy(id="bob:search_input")
        assertEquals(MorningReadPolicy.Kind.FOCUS,MorningReadPolicy.discoverGold(listOf(identified,child)).kind)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(identified.copy(focused=true),child)).kind)
        assertEquals(MorningReadPolicy.Kind.SUBMIT,MorningReadPolicy.discoverGold(listOf(identified.copy(focused=true,text="Gold",imeEnter=true))).kind)
    }
}
