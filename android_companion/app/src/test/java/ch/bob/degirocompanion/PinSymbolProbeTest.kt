package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class PinSymbolProbeTest {
    private fun keys() = (0..9).map { n ->
        PinSymbolProbe.Node((if(n==0) 1 else (n-1)%3)*100f,
            (if(n==0) 3 else (n-1)/3)*100f, 50f, 50f, n, true, true)
    }
    private fun icon(label: Boolean = false, action: Boolean = true) =
        PinSymbolProbe.Node(200f,300f,50f,50f,null,label,action)
    @Test fun distinguishesPresenceLabelsAndActionsWithoutIdentifyingDelete() {
        assertEquals(PinProbePolicy.Result.SYMBOL_NODE_UNAVAILABLE, PinSymbolProbe.classify(keys()))
        assertEquals(PinProbePolicy.Result.SYMBOL_UNLABELLED_ACTION, PinSymbolProbe.classify(keys()+icon()))
        assertEquals(PinProbePolicy.Result.SYMBOL_LABELLED_ACTION, PinSymbolProbe.classify(keys()+icon(true)))
        assertEquals(PinProbePolicy.Result.SYMBOL_NO_ACTION, PinSymbolProbe.classify(keys()+icon(action=false)))
    }
    @Test fun refusesMissingDuplicateOrShuffledKeypads() {
        assertEquals(PinProbePolicy.Result.SYMBOL_LAYOUT_UNCONFIRMED, PinSymbolProbe.classify(keys().drop(1)))
        assertEquals(PinProbePolicy.Result.SYMBOL_LAYOUT_UNCONFIRMED, PinSymbolProbe.classify(keys()+keys()[0]))
        assertEquals(PinProbePolicy.Result.SYMBOL_LAYOUT_UNCONFIRMED,
            PinSymbolProbe.classify(keys().map { if(it.digit==5) it.copy(x=900f) else it }))
    }
    @Test fun doesNotPromoteContainersOrUnrelatedAreas() {
        assertEquals(PinProbePolicy.Result.SYMBOL_NODE_UNAVAILABLE,
            PinSymbolProbe.classify(keys()+icon().copy(width=1000f)))
        assertEquals(PinProbePolicy.Result.SYMBOL_NODE_UNAVAILABLE,
            PinSymbolProbe.classify(keys()+icon().copy(y=-300f)))
        assertEquals(PinProbePolicy.Result.SYMBOL_NODES_MULTIPLE,
            PinSymbolProbe.classify(keys()+icon()+icon().copy(width=30f)))
    }
    @Test fun worksAfterScalingAndTranslation() {
        val nodes=(keys()+icon()).map { it.copy(x=it.x*2+70,y=it.y*2+120,width=it.width*2,height=it.height*2) }
        assertEquals(PinProbePolicy.Result.SYMBOL_UNLABELLED_ACTION, PinSymbolProbe.classify(nodes))
    }
}
