package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningListRegionsTest {
    private val ids=listOf("DE000SQ02JQ6","DE000FG8NHQ3","DE000FB0CVV9")
    private fun candidates()=ids.flatMapIndexed { index,id ->
        val y=100+index*200
        listOf(MorningListRegions.Candidate("SG Gold Turbo | $id",y,y+80),
            MorningListRegions.Candidate(id,y+55,y+75))
    }

    @Test fun nestedAppIdentityBoxesProduceStableLocalContextWithoutNeighbourIsins() {
        val anchors=MorningListRegions.anchors(candidates(),ids,1000)!!
        assertEquals(listOf(155,355,555),anchors.map { it.top })
        assertEquals(listOf(175,375,575),anchors.map { it.bottom })
        assertEquals(anchors,MorningListRegions.anchors(candidates().reversed(),ids,1000))
        val stable=MorningListRegions.stable(anchors,anchors.toList(),ids,1000)!!
        val bands=MorningListRegions.bands(stable,ids,1000)!!
        assertEquals(listOf(0,175,375),bands.map { it.top })
        assertEquals(listOf(355,555,1000),bands.map { it.bottom })
        for((index,band) in bands.withIndex()) {
            assertTrue(band.top<=anchors[index].top && band.bottom>=anchors[index].bottom)
            assertTrue(anchors.withIndex().filter { it.index!=index }.none {
                it.value.top>=band.top && it.value.bottom<=band.bottom })
        }
    }

    @Test fun changedMissingAmbiguousOrUnsafeAnchorsAreRejected() {
        val anchors=MorningListRegions.anchors(candidates(),ids,1000)!!
        assertNull(MorningListRegions.stable(anchors,anchors.mapIndexed { i,a -> if(i==1)a.copy(top=a.top+1) else a },ids,1000))
        assertNull(MorningListRegions.stable(anchors,null,ids,1000))
        assertNull(MorningListRegions.anchors(candidates().filterNot { it.text.contains(ids[1]) },ids,1000))
        assertNull(MorningListRegions.anchors(candidates()+MorningListRegions.Candidate(ids[0],800,820),ids,1000))
        assertNull(MorningListRegions.anchors(candidates().map { it.copy(safe=false) },ids,1000))
        assertNull(MorningListRegions.anchors(candidates().map { it.copy(top=-1) },ids,1000))
        assertNull(MorningListRegions.anchors(candidates(),ids.reversed(),1000))
        assertNull(MorningListRegions.bands(anchors.dropLast(1),ids,1000))
    }

    @Test fun appAnchorsRemoveTheOcrSeedDependencyButCannotReplaceOpticalIdentityEvidence() {
        val id=ids.first()
        val optical=listOf(MorningOcrLayout.Line("SG Gold Turbo BEST Open-End Call BAR 4000 BP 4000 Bv 10 |",10,100,600,120),
            MorningOcrLayout.Line("Societe Generale OTC EUR",10,200,600,220))
        // This is the actual observed failure CLASS: no readable expected
        // optical identity, despite an independently readable app identity.
        assertNull(MorningOcrLayout.productBands(optical,listOf(id),1000))
        val app=MorningListRegions.anchors(listOf(MorningListRegions.Candidate(id,150,170)),listOf(id),1000)!!
        assertNotNull(MorningListRegions.bands(MorningListRegions.stable(app,app,listOf(id),1000),listOf(id),1000))
        assertNull(MorningLocalOcr.productRows(MorningOcrLayout.readingOrder(optical)!!,listOf(id)))
        val actual="SG Gold Turbo BEST Open-End Call BAR 4000 BP 4000 Bv 10 | $id Societe Generale OTC EUR"
        assertEquals(listOf(actual),MorningLocalOcr.productRows(actual,listOf(id)))
        // A crop containing two complete products is never one row.
        val extra=actual.replace(id,ids[1])
        assertNull(MorningLocalOcr.productRows(actual+" "+extra,listOf(id)))
    }
}
