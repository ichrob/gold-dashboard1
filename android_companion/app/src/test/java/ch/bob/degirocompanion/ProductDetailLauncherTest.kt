package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductDetailLauncherTest {
    private val target="DE000FD0S0G4"
    private val launcher=MorningReadPolicy.Node("Order platzieren",clickable=true)
    private val header=listOf(MorningReadPolicy.Node(target),MorningReadPolicy.Node("Übersicht"),
        MorningReadPolicy.Node("SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10 LV 27.07"),launcher)
    private fun lines(nodes:List<MorningReadPolicy.Node>)=nodes.mapIndexed { i,n ->
        QuoteLayout.Line(n.text,0,i*50,500,i*50+30)
    }
    @Test fun isolatedLauncherPermitsOnlyIdentifiedProductReading() {
        assertEquals(3,MorningReadPolicy.detailLauncherIndex(header,target))
        assertEquals(MorningReadPolicy.Kind.READ,MorningReadPolicy.decide(header,target).kind)
        assertEquals(-1,MorningReadPolicy.decide(header,target).index)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(header).kind)
        assertNull(MorningReadPolicy.resultTapIndex(header,target))
        assertNull(MorningReadPolicy.detailLauncherIndex(header,"DE000FE2JJ20"))
        assertNull(MorningReadPolicy.detailLauncherIndex(header,"invalid"))
        assertNull(MorningReadPolicy.detailLauncherIndex(header.filter { it.text!="Übersicht" },target))
        assertNull(MorningReadPolicy.detailLauncherIndex(header+MorningReadPolicy.Node("DE000FE2JJ20"),target))
    }
    @Test fun formsAndCompoundLaunchersNeverBecomeReadable() {
        val bad=listOf(MorningReadPolicy.Node("Order bestätigen"),MorningReadPolicy.Node("confirm order"),
            MorningReadPolicy.Node("Limitpreis"),MorningReadPolicy.Node("order type"),
            MorningReadPolicy.Node("",editable=true,id="quantity"),MorningReadPolicy.Node("",password=true),
            MorningReadPolicy.Node("",sensitive=true),MorningReadPolicy.Node("Login"))
        for(extra in bad) {
            val nodes=header+extra
            assertNull(MorningReadPolicy.detailLauncherIndex(nodes,target,true))
            val raw=lines(nodes)
            assertSame(raw,MorningReadPolicy.detailReadLines(nodes,raw,target,true))
        }
        for(changed in listOf(launcher.copy(text="Order bestätigen"),
            launcher.copy(description="Confirm order"),launcher.copy(row="Order platzieren\n$target"),
            launcher.copy(clickable=false),launcher.copy(containsInput=true)))
            assertNull(MorningReadPolicy.detailLauncherIndex(header.dropLast(1)+changed,target,true))
        assertNull(MorningReadPolicy.detailLauncherIndex(header+launcher,target,true))
        assertNull(MorningReadPolicy.detailLauncherIndex(header+MorningReadPolicy.Node("Kauf",parent=3),target,true))
    }
    @Test fun missingIdentityRequiresAnchoredQuoteSection() {
        val scrolled=listOf(MorningReadPolicy.Node("Kursdaten"),MorningReadPolicy.Node("Geld EUR 10,20"),
            MorningReadPolicy.Node("Brief EUR 10,30"),launcher)
        assertNull(MorningReadPolicy.detailLauncherIndex(scrolled,target))
        assertEquals(3,MorningReadPolicy.detailLauncherIndex(scrolled,target,true))
        assertNull(MorningReadPolicy.detailLauncherIndex(scrolled.filter { it.text!="Kursdaten" },target,true))
        assertNull(MorningReadPolicy.detailLauncherIndex(scrolled.filter { !it.text.startsWith("Brief") },target,true))
        assertNull(MorningReadPolicy.detailLauncherIndex(scrolled+MorningReadPolicy.Node("DE000FE2JJ20"),target,true))
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(scrolled,target).kind)
    }
    @Test fun headerQuoteAndReturnTransactionKeepsLauncherOutOfEvidence() {
        val reader=ProductPageReader()
        val at="2026-10-30T08:00:00Z"
        val raw=lines(header)
        assertEquals(ProductScreenEvidence.Reason.LOGIN_OR_ORDER,
            ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE,raw,at).reason)
        val top=MorningReadPolicy.detailReadLines(header,raw,target)
        assertEquals(ProductPageReader.Move.FORWARD,reader.inspect(1,top,at,false,true,true,requireParameters=true).move)
        val quotes=listOf(MorningReadPolicy.Node("Kursdaten"),MorningReadPolicy.Node("Geld EUR 10,20"),
            MorningReadPolicy.Node("Brief EUR 10,30"),launcher)
        val middle=MorningReadPolicy.detailReadLines(quotes,lines(quotes),target,reader.sameWindow(1))
        val back=reader.inspect(1,middle,at,false,true,true,requireParameters=true)
        assertEquals(ProductPageReader.Move.BACKWARD,back.move)
        assertEquals("",back.result.draft)
        val done=reader.inspect(1,top,at,false,true,true,requireParameters=true)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("Geld (Anzeige ungeprüft): 10,20"))
        assertTrue(done.result.draft.contains("Hebel (Anzeige ungeprüft): 27,07"))
        assertFalse(done.result.draft.contains("Order platzieren"))
        // A compound label appearing during traversal is never stripped.
        val changed=raw+QuoteLayout.Line("Order platzieren jetzt bestätigen",0,900,500,930)
        assertEquals(ProductScreenEvidence.Reason.LOGIN_OR_ORDER,ProductScreenEvidence.read(
            ProductScreenEvidence.PACKAGE,MorningReadPolicy.detailReadLines(header,changed,target),at).reason)
    }
}
