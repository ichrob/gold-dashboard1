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
            p.Node(if(otherIsin)"DE000FB0A491" else draft.isin),
            p.Node("Order platzieren",clickable=true),
            p.Node("Kauf",clickable=true,selected=!selectedSell),
            p.Node("Verkauf",clickable=true,selected=selectedSell),
            p.Node("Ordertyp"),
            p.Node(type,clickable=true)
        )
        if(modal) n.addAll(listOf(p.Node("Market",clickable=true),p.Node("Stop Loss",clickable=true),p.Node("Stop Limit",clickable=true)))
        if(type=="Stop Loss") {
            n.add(p.Node("Stop (€)",left=380,top=500,right=600,bottom=525))
            n.add(p.Node("",editable=true,input=stop,left=380,top=555,right=620,bottom=600))
            n.add(p.Node("Anzahl",left=30,top=650,right=180,bottom=675))
            n.add(p.Node("",editable=true,input=quantity,left=30,top=700,right=270,bottom=745))
        }
        return p.Frame("nl.degiro.trader",n)
    }
    @Test fun payloadDoesNotAcceptStaleWrongCurrencyOrArbitraryNumbers() {
        val text="BOB-STOP/1|DE000FB0A490|EUR|3|26.90|$now"
        assertEquals(2690,StopLossDraftCodec.parse(text,now)?.stopCents)
        assertNull(StopLossDraftCodec.parse(text.replace("EUR","CHF"),now))
        assertNull(StopLossDraftCodec.parse(text,now+300_001))
        assertNull(StopLossDraftCodec.parse(text.replace("|3|","|-3|"),now))
        assertNull(StopLossDraftCodec.parse(text.replace("26.90","26.999"),now))
    }
    @Test fun noBuyNoWrongIsinNoLoginNoSubmit() {
        val p=StopLossPrefillPolicy
        assertEquals(p.Kind.BLOCK,p.decide(p.Stage.ORDER_TYPE,frame(selectedSell=false),draft).kind)
        assertEquals(p.Kind.BLOCK,p.decide(p.Stage.ORDER_TYPE,frame(otherIsin=true),draft).kind)
        val passwordFrame=frame().copy(nodes=frame().nodes+p.Node("PIN eingeben"))
        assertEquals(p.Kind.BLOCK,p.decide(p.Stage.ORDER_TYPE,passwordFrame,draft).kind)
        assertEquals(p.Kind.BLOCK,p.decide(p.Stage.ORDER_TYPE,frame().copy(app="com.example.other"),draft).kind)
    }
    @Test fun orderTypeAndFieldsOnly() {
        val p=StopLossPrefillPolicy
        assertEquals(p.Kind.CLICK,p.decide(p.Stage.ORDER_TYPE,frame(),draft).kind)
        val option=p.decide(p.Stage.CHOOSE_STOP,frame(modal=true),draft)
        assertEquals(p.Kind.CLICK,option.kind)
        assertEquals("Stop Loss",frame(modal=true).nodes[option.index].label)
        val stop=p.decide(p.Stage.WRITE_STOP,frame(type="Stop Loss"),draft)
        assertEquals(p.Kind.WRITE,stop.kind)
        assertEquals("26,90",stop.text)
        assertEquals(p.Kind.ADVANCE,p.decide(p.Stage.VERIFY_STOP,frame(type="Stop Loss",stop="26,90"),draft).kind)
        val qty=p.decide(p.Stage.WRITE_QUANTITY,frame(type="Stop Loss",stop="26,90"),draft)
        assertEquals(p.Kind.WRITE,qty.kind)
        assertEquals("3",qty.text)
        assertEquals(p.Kind.DONE,p.decide(p.Stage.VERIFY_QUANTITY,frame(type="Stop Loss",stop="26,90",quantity="3"),draft).kind)
        assertEquals(p.Kind.BLOCK,p.decide(p.Stage.VERIFY_QUANTITY,frame(type="Stop Loss",stop="26,90",quantity="2"),draft).kind)
    }
}
