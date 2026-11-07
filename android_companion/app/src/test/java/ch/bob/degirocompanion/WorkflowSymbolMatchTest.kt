package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowSymbolMatchTest {
    private val width = 160
    private val height = 240
    private fun screen(vararg positions: Pair<Int, Int>): IntArray = IntArray(width * height) { 255 }.also { pixels ->
        positions.forEach { (x, y) -> for (dy in 0 until 32) for (dx in 0 until 32) {
            if (dx in 4..10 || dy in 4..10 || (dx in 20..26 && dy in 20..26)) pixels[(y + dy) * width + x + dx] = 0
        } }
    }
    private fun pattern() = WorkflowSymbolMatch.pattern(screen(10 to 20), width, height, SymbolBox(10,20,42,52))!!
    @Test fun findsMovedSymbolInsideClickableElement() {
        assertEquals(0, WorkflowSymbolMatch.match(pattern(), screen(90 to 140), width, height, listOf(SymbolBox(88,138,126,176))))
    }
    @Test fun duplicatesMissingAndRotatedScreenDoNotAuthorizeClick() {
        assertNull(WorkflowSymbolMatch.match(pattern(), screen(10 to 20,90 to 140), width,height,listOf(SymbolBox(10,20,42,52),SymbolBox(90,140,122,172))))
        assertNull(WorkflowSymbolMatch.match(pattern(), screen(),width,height,listOf(SymbolBox(10,20,42,52))))
        assertNull(WorkflowSymbolMatch.match(pattern(),IntArray(width*height),height,width,listOf(SymbolBox(10,20,42,52))))
    }
    @Test fun blankOrOversizedTrainingRegionsAreRejected() {
        assertNull(WorkflowSymbolMatch.pattern(screen(),width,height,SymbolBox(10,20,42,52)))
        assertNull(WorkflowSymbolMatch.pattern(screen(10 to 20),width,height,SymbolBox(0,0,width,height)))
        assertNull(WorkflowSymbolMatch.pattern(screen(),width,height,SymbolBox(-1,0,32,32)))
    }
}
