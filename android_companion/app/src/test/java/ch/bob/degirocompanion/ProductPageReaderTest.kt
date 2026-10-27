package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductPageReaderTest {
    private val at = "2026-10-27T17:00:00Z"
    private fun lines(vararg text: String) = text.mapIndexed { i, v -> QuoteLayout.Line(v, 0, i * 50, 500, i * 50 + 30) }
    private val header = lines("DE000FD0S0G4", "EUR")
    private val quotes = lines("Geld EUR 10,20", "Brief EUR 10,30")
    private fun step(reader: ProductPageReader, data: List<QuoteLayout.Line>, forward: Boolean = true, backward: Boolean = true, window: Int = 1, sensitive: Boolean = false) = reader.inspect(window, data, at, sensitive, forward, backward)
    @Test fun doesNotPublishUntilItReturnsToSameHeader() {
        val r = ProductPageReader()
        assertEquals(ProductPageReader.Move.FORWARD, step(r, header).move)
        val down = step(r, quotes, forward = false)
        assertEquals(ProductPageReader.Move.BACKWARD, down.move)
        assertEquals("", down.result.draft)
        val done = step(r, header)
        assertEquals(ProductPageReader.Move.FINISHED, done.move)
        assertTrue(done.result.draft.contains("ISIN: DE000FD0S0G4"))
        assertTrue(done.result.draft.contains("Geld (Anzeige ungeprüft): 10,20"))
        assertFalse(r.anchored)
    }
    @Test fun abortsForIdentityWindowAndProtectedViewChanges() {
        for (kind in 0..3) {
            val r = ProductPageReader(); step(r, header)
            val out = when (kind) {
                0 -> step(r, lines("DE000FE2JJ20", "Geld EUR 10,20"))
                1 -> step(r, quotes, window = 2)
                2 -> step(r, quotes, sensitive = true)
                else -> step(r, quotes + lines("Ordertyp"))
            }
            assertEquals(ProductPageReader.Move.ABORT, out.move)
            assertEquals("", out.result.draft)
            assertFalse(r.anchored)
        }
    }
    @Test fun missingIdentityCannotStartAndReturnFailureDiscardsDraft() {
        val r = ProductPageReader()
        assertEquals(ProductPageReader.Move.NONE, step(r, quotes).move)
        step(r, header)
        assertEquals(ProductPageReader.Move.ABORT, step(r, quotes, forward = false, backward = false).move)
        assertFalse(r.anchored)
    }
    @Test fun boundsScrollsAndRejectsInconsistentQuotes() {
        val r = ProductPageReader()
        repeat(8) { assertEquals(ProductPageReader.Move.FORWARD, step(r, header).move) }
        assertEquals(ProductPageReader.Move.ABORT, step(r, header).move)
        step(r, header)
        assertEquals(ProductPageReader.Move.ABORT, step(r, lines("Geld EUR 12,00", "Brief EUR 11,00"), forward = false).move)
    }
    @Test fun failedForwardActionReturnsToHeaderButFailedReturnNeverPublishes() {
        val r = ProductPageReader(); step(r, header); step(r, quotes)
        r.scrollFailed(ProductPageReader.Move.FORWARD)
        assertEquals(ProductPageReader.Move.BACKWARD, step(r, quotes).move)
        r.scrollFailed(ProductPageReader.Move.BACKWARD)
        assertEquals(ProductPageReader.Move.ABORT, step(r, quotes).move)
    }
}
