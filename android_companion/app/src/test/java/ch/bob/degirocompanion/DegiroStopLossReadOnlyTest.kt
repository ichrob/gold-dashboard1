package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class DegiroStopLossReadOnlyTest {
    private fun node(label:String="",selected:Boolean=false,password:Boolean=false,
                     editable:Boolean=false)=DegiroStopLossReadOnly.Node(
                         label,selected,password,editable)
    private fun frame(vararg nodes:DegiroStopLossReadOnly.Node)=
        DegiroStopLossReadOnly.Frame("nl.degiro.trader",nodes.toList())
    private val isin="DE000FB0A490"
    private fun detail()=frame(node(isin),node("Übersicht"),node("KAUF"),node("VERKAUF"))

    @Test fun onlyRealForegroundDegiroAndUnprotectedTree() {
        assertEquals(DegiroStopLossReadOnly.Code.NOT_DEGIRO,
            DegiroStopLossReadOnly.inspect(detail().copy(packageName="com.example.mock")).code)
        assertEquals(DegiroStopLossReadOnly.Code.PROTECTED,
            DegiroStopLossReadOnly.inspect(detail().copy(nodes=detail().nodes+node("PIN eingeben"))).code)
        assertEquals(DegiroStopLossReadOnly.Code.PROTECTED,
            DegiroStopLossReadOnly.inspect(detail().copy(nodes=detail().nodes+node(password=true))).code)
        assertEquals(DegiroStopLossReadOnly.Code.INCOMPLETE,
            DegiroStopLossReadOnly.inspect(frame(node(isin))).code)
    }
    @Test fun detailIsDetectedWithoutAnyOrderOrRawBrokerData() {
        val r=DegiroStopLossReadOnly.inspect(detail())
        assertEquals(DegiroStopLossReadOnly.Code.PRODUCT_DETAIL,r.code)
        assertTrue(r.terminal)
        assertFalse(r.message.contains(isin))
        assertFalse(r.message.contains("25,90"))
    }
    @Test fun sellFormIsOnlyRecognizedWithUniqueCaptions() {
        val view=frame(node(isin),node("Order platzieren"),node("Kauf"),
            node("Verkauf",selected=true),node("Ordertyp"),node("Stop Loss"),
            node("Stop (€)"),node("Anzahl"),node(editable=true,label="sehr vertraulich"))
        val r=DegiroStopLossReadOnly.inspect(view)
        assertEquals(DegiroStopLossReadOnly.Code.SELL_FORM,r.code)
        assertFalse(r.message.contains(isin))
        assertFalse(r.message.contains("vertraulich"))
        assertEquals(DegiroStopLossReadOnly.Code.SELL_FORM_UNCLEAR,
            DegiroStopLossReadOnly.inspect(view.copy(nodes=view.nodes+node("Stop (€)"))).code)
    }
    @Test fun buyAndMultipleIsinsAreBlocked() {
        val view=frame(node(isin),node("Order platzieren"),node("Kauf",selected=true),
            node("Verkauf"),node("Ordertyp"),node("Stop Loss"),node("Stop (€)"),node("Anzahl"))
        assertEquals(DegiroStopLossReadOnly.Code.BUY_OR_UNKNOWN_SIDE,
            DegiroStopLossReadOnly.inspect(view).code)
        assertEquals(DegiroStopLossReadOnly.Code.MULTIPLE_ISINS,
            DegiroStopLossReadOnly.inspect(view.copy(nodes=view.nodes+node("DE000FB0A491"))).code)
    }
    @Test fun orderConfirmationIsRecognizedButNeverApprovedOrActedOn() {
        val view=frame(node(isin),node("Order platzieren"),
            node("Order bestätigen"),node("Ordertyp"),
            node("Stückzahl"),node(editable=true,label="private-value"))
        val result=DegiroStopLossReadOnly.inspect(view)
        assertEquals(DegiroStopLossReadOnly.Code.ORDER_CONFIRMATION_VISIBLE,result.code)
        assertTrue(result.terminal)
        assertFalse(result.message.contains(isin))
        assertFalse(result.message.contains("private-value"))
        assertEquals(DegiroStopLossReadOnly.Code.PROTECTED,
            DegiroStopLossReadOnly.inspect(view.copy(
                nodes=view.nodes+node(password=true))).code)
    }

    @Test fun orderFieldsMayBeRecognizedAsLabelsButNeverEntered() {
        val view=frame(node(isin),node("Order platzieren"),
            node("Ordertyp"),node("Limitpreis"),node("Stückzahl"),
            node(editable=true,label="1234"))
        val result=DegiroStopLossReadOnly.inspect(view)
        assertEquals(DegiroStopLossReadOnly.Code.ORDER_FIELDS_VISIBLE_READ_ONLY,result.code)
        assertTrue(result.terminal)
        assertFalse(result.message.contains("1234"))
        assertEquals(DegiroStopLossReadOnly.Code.BUY_OR_UNKNOWN_SIDE,
            DegiroStopLossReadOnly.inspect(view.copy(
                nodes=view.nodes+node("Kauf",selected=true))).code)
        assertEquals(DegiroStopLossReadOnly.Code.MULTIPLE_ISINS,
            DegiroStopLossReadOnly.inspect(view.copy(
                nodes=view.nodes+node("DE000FB0A491"))).code)
    }

    @Test fun explicitSessionHasBoundedDeadlineAndOnlyCodes() {
        DegiroReadOnlySession.finish("STOPP")
        assertTrue(DegiroReadOnlySession.start(1000))
        assertFalse(DegiroReadOnlySession.start(2000))
        assertTrue(DegiroReadOnlySession.active(45999))
        DegiroReadOnlySession.note(DegiroStopLossReadOnly.Result(
            DegiroStopLossReadOnly.Code.PRODUCT_DETAIL))
        assertFalse(DegiroReadOnlySession.active(46000))
        assertEquals("PRODUCT_DETAIL",DegiroReadOnlySession.lastCode)
        assertFalse(DegiroReadOnlySession.status.contains(isin))
        assertTrue(DegiroReadOnlySession.start(50000))
        assertFalse(DegiroReadOnlySession.active(95000))
        assertEquals("ZEITLIMIT",DegiroReadOnlySession.lastCode)
    }
}
