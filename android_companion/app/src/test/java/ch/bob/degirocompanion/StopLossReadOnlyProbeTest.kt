package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

/** Tests read-only semantic recognition; never requires DEGIRO or account data. */
class StopLossReadOnlyProbeTest {
    private val p=StopLossReadOnlyProbe
    private val isin="DE000FB0A490"
    private fun n(label:String="",selected:Boolean=false,password:Boolean=false,
                  editable:Boolean=false) =
        StopLossPrefillPolicy.Node(label=label,selected=selected,
            password=password,editable=editable)
    private fun frame(vararg nodes:StopLossPrefillPolicy.Node,
                      app:String="nl.degiro.trader")=
        StopLossPrefillPolicy.Frame(app,nodes.toList())
    private fun detail()=frame(
        n(isin),n("Übersicht"),n("KAUF"),n("VERKAUF"))

    @Test fun rejectsOtherAppAndLoginAndIncompleteTree() {
        assertEquals(StopLossReadOnlyProbe.Code.NOT_DEGIRO,
            p.inspect(detail().copy(app="com.example.other")).code)
        assertEquals(StopLossReadOnlyProbe.Code.SCREEN_PROTECTED,
            p.inspect(detail().copy(nodes=detail().nodes+n("PIN eingeben"))).code)
        assertEquals(StopLossReadOnlyProbe.Code.SCREEN_PROTECTED,
            p.inspect(detail().copy(nodes=detail().nodes+n(password=true))).code)
        assertEquals(StopLossReadOnlyProbe.Code.VIEW_INCOMPLETE,
            p.inspect(frame(n(isin))).code)
    }
    @Test fun recognizesProductDetailWithoutClickOrOrder() {
        val r=p.inspect(detail())
        assertEquals(StopLossReadOnlyProbe.Code.PRODUCT_DETAIL_VISIBLE,r.code)
        assertFalse(r.stopCaptionVisible)
        assertFalse(r.quantityCaptionVisible)
        assertFalse(r.stopLossVisible)
        assertFalse(r.summary.contains(isin))
    }
    @Test fun detectsVisibleSellFormButNeverProducesAnAction() {
        val r=p.inspect(frame(
            n(isin),n("Order platzieren"),n("Kauf"),
            n("Verkauf",selected=true),n("Ordertyp"),
            n("Stop Loss"),n("Stop (€)"),n("Anzahl"),
            n("untrusted broker value 99,99",editable=true),
            n("untrusted account field",editable=true)
        ))
        assertEquals(StopLossReadOnlyProbe.Code.SELL_FORM_VISIBLE,r.code)
        assertTrue(r.stopCaptionVisible)
        assertTrue(r.quantityCaptionVisible)
        assertTrue(r.stopLossVisible)
        val status=r.summary
        assertFalse(status.contains(isin))
        assertFalse(status.contains("99,99"))
        assertFalse(status.contains("untrusted"))
    }
    @Test fun refusesBuyAmbiguousProductAndUnclearFields() {
        val sell=frame(n(isin),n("Order platzieren"),n("Kauf"),
            n("Verkauf",selected=true),n("Ordertyp"),
            n("Stop Loss"),n("Stop (€)"),n("Anzahl"))
        val buy=sell.copy(nodes=sell.nodes.map {
            if(it.label=="Kauf")it.copy(selected=true)
            else if(it.label=="Verkauf")it.copy(selected=false) else it
        })
        assertEquals(StopLossReadOnlyProbe.Code.BUY_OR_UNCONFIRMED_FORM,p.inspect(buy).code)
        assertEquals(StopLossReadOnlyProbe.Code.AMBIGUOUS_ISIN,p.inspect(
            sell.copy(nodes=sell.nodes+n("DE000FB0A491"))).code)
        assertEquals(StopLossReadOnlyProbe.Code.SELL_FORM_LABELS_UNCLEAR,p.inspect(
            sell.copy(nodes=sell.nodes.filterNot { it.label=="Anzahl" })).code)
        assertEquals(StopLossReadOnlyProbe.Code.SELL_FORM_LABELS_UNCLEAR,p.inspect(
            sell.copy(nodes=sell.nodes+n("Stop (€)"))).code)
    }
    @Test fun timeBoundedRAMOnlySessionNeverReturnsBrokerData() {
        val s=StopLossReadOnlySession
        s.finish("STOPP")
        assertTrue(s.start(300L))
        assertFalse(s.start(301L))
        assertTrue(s.active(44_999L))
        s.observe(p.inspect(detail()))
        assertFalse(s.active(45_300L))
        assertEquals(StopLossReadOnlyProbe.Code.PRODUCT_DETAIL_VISIBLE,s.result?.code)
        assertFalse(s.status.contains(isin))
        assertTrue(s.start(100_000L))
        assertTrue(s.active(144_999L))
        assertFalse(s.active(145_000L))
        assertTrue(s.status.contains("Zeitlimit"))
        s.finish("STOPP")
    }
}
