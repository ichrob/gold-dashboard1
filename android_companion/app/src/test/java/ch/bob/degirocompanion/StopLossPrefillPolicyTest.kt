package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class StopLossPrefillPolicyTest {
    private val now = 1_800_000_000_000L
    private val draft = StopLossPrefillDraft("DE000FB0A490",3,2690,now)
    private fun frame(selectedSell:Boolean=true, otherIsin:Boolean=false, modal:Boolean=false,
                      stop:String="", quantity:String="", type:String="Limit"): StopLossPrefillPolicy.Frame {
        val p=StopLossPrefillPolicy
        val n=mutableListOf(
            StopLossPrefillPolicy.Node(if(otherIsin)"DE000FB0A491" else draft.isin),
            StopLossPrefillPolicy.Node("Order platzieren",clickable=true),
            StopLossPrefillPolicy.Node("Kauf",clickable=true,selected=!selectedSell),
            StopLossPrefillPolicy.Node("Verkauf",clickable=true,selected=selectedSell),
            StopLossPrefillPolicy.Node("Ordertyp"),
            StopLossPrefillPolicy.Node(type,clickable=true)
        )
        if(modal) n.addAll(listOf(StopLossPrefillPolicy.Node("Market",clickable=true),StopLossPrefillPolicy.Node("Stop Loss",clickable=true),StopLossPrefillPolicy.Node("Stop Limit",clickable=true)))
        if(type=="Stop Loss") {
            n.add(StopLossPrefillPolicy.Node("Stop (€)",left=380,top=500,right=600,bottom=525))
            n.add(StopLossPrefillPolicy.Node("",editable=true,input=stop,left=380,top=555,right=620,bottom=600))
            n.add(StopLossPrefillPolicy.Node("Anzahl",left=30,top=650,right=180,bottom=675))
            n.add(StopLossPrefillPolicy.Node("",editable=true,input=quantity,left=30,top=700,right=270,bottom=745))
        }
        return StopLossPrefillPolicy.Frame("nl.degiro.trader",n)
    }
    @Test fun payloadDoesNotAcceptStaleWrongCurrencyOrArbitraryNumbers() {
        val text="BOB-STOP/1|DE000FB0A490|EUR|3|26.90|$now"
        assertEquals(2690L,StopLossDraftCodec.parse(text,now)?.stopCents)
        assertNull(StopLossDraftCodec.parse(text.replace("EUR","CHF"),now))
        assertNull(StopLossDraftCodec.parse(text,now+300_001))
        assertNull(StopLossDraftCodec.parse(text.replace("|3|","|-3|"),now))
        assertNull(StopLossDraftCodec.parse(text.replace("26.90","26.999"),now))
    }
    @Test fun detailMayOpenOnlySellFormForExactIsin() {
        val p=StopLossPrefillPolicy
        val detail=StopLossPrefillPolicy.Frame("nl.degiro.trader",listOf(
            StopLossPrefillPolicy.Node(draft.isin),StopLossPrefillPolicy.Node("Übersicht"),
            StopLossPrefillPolicy.Node("KAUF",clickable=true),StopLossPrefillPolicy.Node("VERKAUF",clickable=true)
        ))
        val allowed=p.decide(StopLossPrefillPolicy.Stage.OPEN_FORM,detail,draft)
        assertEquals(StopLossPrefillPolicy.Kind.CLICK,allowed.kind)
        assertEquals("VERKAUF",detail.nodes[allowed.index].label)
        assertEquals(StopLossPrefillPolicy.Stage.VERIFY_FORM,allowed.next)
        assertEquals(StopLossPrefillPolicy.Kind.ADVANCE,p.decide(StopLossPrefillPolicy.Stage.OPEN_FORM,frame(),draft).kind)
        assertEquals(StopLossPrefillPolicy.Kind.ADVANCE,p.decide(StopLossPrefillPolicy.Stage.VERIFY_FORM,frame(),draft).kind)
        assertEquals(StopLossPrefillPolicy.Kind.BLOCK,p.decide(StopLossPrefillPolicy.Stage.OPEN_FORM,detail.copy(
            nodes=detail.nodes.filterNot { it.label=="Übersicht" }),draft).kind)
        assertEquals(StopLossPrefillPolicy.Kind.BLOCK,p.decide(StopLossPrefillPolicy.Stage.OPEN_FORM,detail.copy(
            nodes=detail.nodes.map { if(it.label==draft.isin) it.copy(label="DE000FB0A491") else it }),draft).kind)
    }
    @Test fun noBuyNoWrongIsinNoLoginNoSubmit() {
        val p=StopLossPrefillPolicy
        assertEquals(StopLossPrefillPolicy.Kind.BLOCK,p.decide(StopLossPrefillPolicy.Stage.ORDER_TYPE,frame(selectedSell=false),draft).kind)
        assertEquals(StopLossPrefillPolicy.Kind.BLOCK,p.decide(StopLossPrefillPolicy.Stage.ORDER_TYPE,frame(otherIsin=true),draft).kind)
        val passwordFrame=frame().copy(nodes=frame().nodes+StopLossPrefillPolicy.Node("PIN eingeben"))
        assertEquals(StopLossPrefillPolicy.Kind.BLOCK,p.decide(StopLossPrefillPolicy.Stage.ORDER_TYPE,passwordFrame,draft).kind)
        assertEquals(StopLossPrefillPolicy.Kind.BLOCK,p.decide(StopLossPrefillPolicy.Stage.ORDER_TYPE,frame().copy(app="com.example.other"),draft).kind)
    }
    @Test fun orderTypeAndFieldsOnly() {
        val p=StopLossPrefillPolicy
        assertEquals(StopLossPrefillPolicy.Kind.CLICK,p.decide(StopLossPrefillPolicy.Stage.ORDER_TYPE,frame(),draft).kind)
        val option=p.decide(StopLossPrefillPolicy.Stage.CHOOSE_STOP,frame(modal=true),draft)
        assertEquals(StopLossPrefillPolicy.Kind.CLICK,option.kind)
        assertEquals("Stop Loss",frame(modal=true).nodes[option.index].label)
        val stop=p.decide(StopLossPrefillPolicy.Stage.WRITE_STOP,frame(type="Stop Loss"),draft)
        assertEquals(StopLossPrefillPolicy.Kind.WRITE,stop.kind)
        assertEquals("26,90",stop.text)
        assertEquals(StopLossPrefillPolicy.Kind.ADVANCE,p.decide(StopLossPrefillPolicy.Stage.VERIFY_STOP,frame(type="Stop Loss",stop="26,90"),draft).kind)
        val qty=p.decide(StopLossPrefillPolicy.Stage.WRITE_QUANTITY,frame(type="Stop Loss",stop="26,90"),draft)
        assertEquals(StopLossPrefillPolicy.Kind.WRITE,qty.kind)
        assertEquals("3",qty.text)
        assertEquals(StopLossPrefillPolicy.Kind.DONE,p.decide(StopLossPrefillPolicy.Stage.VERIFY_QUANTITY,frame(type="Stop Loss",stop="26,90",quantity="3"),draft).kind)
        assertEquals(StopLossPrefillPolicy.Kind.BLOCK,p.decide(StopLossPrefillPolicy.Stage.VERIFY_QUANTITY,frame(type="Stop Loss",stop="26,90",quantity="2"),draft).kind)
    }
}
