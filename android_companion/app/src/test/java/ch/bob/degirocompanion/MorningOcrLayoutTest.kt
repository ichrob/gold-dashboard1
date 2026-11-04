package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningOcrLayoutTest {
    private fun line(text:String,x:Int,y:Int)=MorningOcrLayout.Line(text,x,y,x+100,y+20)

    @Test fun detachedCurrencyBlocksAreRejoinedToTheirOwnProductFooter() {
        val ids=listOf("DE000SQ02JQ6","DE000FG8NHQ3")
        // Block traversal can emit the right-hand currency column after all
        // left-hand titles/venues. Original strings cannot delimit these rows.
        val blocks=listOf(
            line("SG Gold Turbo Unlimited Mini Call BAR 2166 BP 2125.38 Bv 10 | ${ids[0]}",10,100),
            line("Societe Generale OTC",10,150),
            line("SG Gold Knock-Out Warrant Put BAR 4400 BP 4400 Bv 10 | ${ids[1]}",10,200),
            line("Societe Generale OTC",10,250),
            line("EUR",500,152),line("CHF",500,248))
        assertNull(MorningLocalOcr.productRows(blocks.joinToString("\n") { it.text },ids))
        val ordered=MorningOcrLayout.readingOrder(blocks)!!
        val rows=MorningLocalOcr.productRows(ordered,ids)!!
        assertTrue(rows[0].endsWith("OTC EUR"))
        assertTrue(rows[1].endsWith("OTC CHF"))
        assertEquals(ordered,MorningOcrLayout.readingOrder(blocks.reversed()))
        assertNull(MorningLocalOcr.productRows(ordered,ids.reversed()))
    }

    @Test fun layoutDoesNotRepairMissingOrForeignProductEvidence() {
        val id="DE000SQ02JQ6"
        val lines=listOf(line("SG Gold Turbo Call BAR 2166 BP 2125.38 Bv 10 | $id",10,100),
            line("Societe Generale OTC",10,150),line("Portfolio",500,150))
        assertNull(MorningLocalOcr.productRows(MorningOcrLayout.readingOrder(lines)!!,listOf(id)))
        assertNull(MorningOcrLayout.readingOrder(emptyList()))
        assertNull(MorningOcrLayout.readingOrder(List(301) { line("x",0,it*30) }))
        assertNull(MorningOcrLayout.readingOrder(listOf(line("x".repeat(20001),0,0))))
        assertNull(MorningOcrLayout.readingOrder(listOf(line("x",-1,0))))
    }

    @Test fun fixedAnchorCannotChainAdjacentRowsIntoOneLine() {
        assertEquals("a b\nc",MorningOcrLayout.readingOrder(listOf(
            line("a",0,0),line("b",200,8),line("c",400,16))))
    }
}
