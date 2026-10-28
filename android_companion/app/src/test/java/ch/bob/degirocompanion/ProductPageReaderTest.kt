package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductPageReaderTest {
    private val at = "2026-10-27T17:00:00Z"
    private fun lines(vararg text: String) = text.mapIndexed { i, v -> QuoteLayout.Line(v, 0, i * 50, 500, i * 50 + 30) }
    private val header = lines("DE000FD0S0G4", "EUR")
    private val quotes = lines("Geld EUR 10,20", "Brief EUR 10,30")
    private fun step(reader: ProductPageReader, data: List<QuoteLayout.Line>, forward: Boolean = true, backward: Boolean = true, window: Int = 1, sensitive: Boolean = false) = reader.inspect(window, data, at, sensitive, forward, backward)
    @Test fun transientScrollLayoutCanRecoverWithoutPublishingPartialDraft() {
        val r = ProductPageReader()
        step(r, header)
        val waiting = r.inspect(1, quotes, at, false, false, false, scrollAmbiguous = true)
        assertEquals(ProductPageReader.Move.NONE, waiting.move)
        assertEquals(ProductPageReader.Cause.WAIT_SCROLL_LAYOUT, waiting.cause)
        assertEquals("", waiting.result.draft)
        assertTrue(r.anchored)
        assertEquals(ProductPageReader.Move.BACKWARD, step(r, quotes, forward = false).move)
        val done = step(r, header)
        assertEquals(ProductPageReader.Move.FINISHED, done.move)
        assertTrue(done.result.draft.contains("Geld (Anzeige ungeprüft): 10,20"))
    }
    @Test fun layoutWaitDoesNotHideChangedWindowOrProduct() {
        for (changedWindow in listOf(false, true)) {
            val r = ProductPageReader()
            step(r, header)
            val changed = r.inspect(if (changedWindow) 2 else 1,
                if (changedWindow) quotes else lines("DE000FE2JJ20"), at, false, false, false, scrollAmbiguous = true)
            assertEquals(ProductPageReader.Move.ABORT, changed.move)
            assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED, changed.cause)
            assertEquals("", changed.result.draft)
        }
    }

    @Test fun returnedHeaderAddsParametersOnlyAfterIdentityRecheck() {
        val r = ProductPageReader()
        val title = lines("DE000FG77MY4", "SG Gold Turbo BEST Open-End Put BAR",
            "4181.33 BP 4181.33 Bv 10 LV 32.33")
        step(r, title)
        assertEquals(ProductPageReader.Move.BACKWARD, step(r, quotes, forward = false).move)
        val done = step(r, title)
        assertEquals(ProductPageReader.Move.FINISHED, done.move)
        assertTrue(done.result.draft.contains("Hebel (Anzeige ungeprüft): 32,33"))
        assertTrue(done.result.draft.contains("Bv (Anzeige ungeprüft): 10"))
        step(r, title); step(r, quotes, forward = false)
        val changed = step(r, header)
        assertEquals(ProductPageReader.Move.ABORT, changed.move)
        assertEquals("", changed.result.draft)
    }

    @Test fun waitsForUnanchoredLayoutAndCanThenReadWithoutRestart() {
        val r = ProductPageReader()
        repeat(3) {
            val waiting = r.inspect(1, emptyList(), at, false, false, false, scrollAmbiguous = true)
            assertEquals(ProductPageReader.Move.NONE, waiting.move)
            assertEquals(ProductPageReader.Cause.WAIT_SCROLL_LAYOUT, waiting.cause)
            assertEquals("", waiting.result.draft)
            assertFalse(r.anchored)
        }
        assertEquals(ProductPageReader.Move.FORWARD, step(r, header).move)
        assertEquals(ProductPageReader.Move.BACKWARD, step(r, quotes, forward = false).move)
        assertEquals(ProductPageReader.Move.FINISHED, step(r, header).move)
    }
    @Test fun persistentAmbiguityDiscardsCandidateAndKeepsProtectedChecks() {
        val r = ProductPageReader()
        step(r, header); step(r, quotes)
        repeat(5) {
            val waiting = r.inspect(1, quotes, at, false, false, false, scrollAmbiguous = true)
            assertEquals(ProductPageReader.Move.NONE, waiting.move)
            assertEquals("", waiting.result.draft)
        }
        val abort = r.inspect(1, quotes, at, false, false, false, scrollAmbiguous = true)
        assertEquals(ProductPageReader.Move.ABORT, abort.move)
        assertEquals(ProductPageReader.Cause.SCROLL_LAYOUT_CHANGED, abort.cause)
        assertEquals("", abort.result.draft)
        assertFalse(r.anchored)
        step(r, header)
        val protected = r.inspect(1, quotes, at, true, false, false, scrollAmbiguous = true)
        assertEquals(ProductPageReader.Cause.UNSAFE_VIEW, protected.cause)
    }
    @Test fun ambiguousHeaderCurrencyDoesNotPreventScrollToLabelledQuotes() {
        val r = ProductPageReader()
        val mixedHeader = lines("DE000FD0S0G4", "CHF 500,00", "EUR 10,20")
        assertEquals(ProductPageReader.Move.FORWARD, step(r, mixedHeader).move)
        val down = step(r, quotes, forward = false)
        assertEquals(ProductPageReader.Move.BACKWARD, down.move)
        assertEquals("", down.result.draft)
        val done = step(r, mixedHeader)
        assertEquals(ProductPageReader.Move.FINISHED, done.move)
        assertTrue(done.result.draft.contains("Währung (Anzeige ungeprüft): EUR"))
        assertFalse(done.result.draft.contains("500,00"))
    }
    @Test fun locatesHeaderFromRecognizedQuoteSectionWithoutAssigningValues() {
        val r = ProductPageReader()
        val section = quotes + lines("Kursdaten")
        repeat(4) {
            val seek = step(r, section)
            assertEquals(ProductPageReader.Move.BACKWARD, seek.move)
            assertEquals(ProductPageReader.Cause.SEEK_HEADER, seek.cause)
            assertEquals("", seek.result.draft)
            assertFalse(r.anchored)
        }
        assertEquals(ProductPageReader.Cause.SEEK_LIMIT, step(r, section).cause)
        assertEquals(ProductPageReader.Move.NONE, step(r, quotes).move)
        assertEquals(ProductPageReader.Move.BACKWARD, step(r, section).move)
        assertEquals(ProductPageReader.Move.FORWARD, step(r, header).move)
    }
    @Test fun transientProtectedLaunchDoesNotAbortBeforeIdentity() {
        val r = ProductPageReader()
        val protected = step(r, header, sensitive = true)
        assertEquals(ProductPageReader.Move.NONE, protected.move)
        assertEquals(ProductPageReader.Cause.WAIT_PROTECTED, protected.cause)
        assertEquals("", protected.result.draft)
        assertFalse(r.anchored)
        assertEquals(ProductPageReader.Move.NONE, step(r, lines("Login", "Passwort")).move)
        assertEquals(ProductPageReader.Move.FORWARD, step(r, header).move)
        val after = step(r, quotes, sensitive = true)
        assertEquals(ProductPageReader.Move.ABORT, after.move)
        assertEquals(ProductPageReader.Cause.UNSAFE_VIEW, after.cause)
        assertEquals(ProductScreenEvidence.Reason.PROTECTED, after.result.reason)
    }
    @Test fun waitsForInitialScrollSurfaceWithoutRetainingIdentity() {
        val r = ProductPageReader()
        val pending = step(r, header, forward = false, backward = false)
        assertEquals(ProductPageReader.Move.NONE, pending.move)
        assertEquals(ProductPageReader.Cause.WAIT_SCROLL, pending.cause)
        assertFalse(r.anchored)
        assertEquals(ProductPageReader.Move.FORWARD, step(r, header).move)
    }
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
    @Test fun transientRejectedActionsRetryAndStillRequireHeaderRecheck() {
        val r = ProductPageReader(); step(r, header)
        r.scrollFailed(ProductPageReader.Move.FORWARD)
        assertEquals(ProductPageReader.Move.FORWARD, step(r, header).move)
        r.scrollSucceeded(ProductPageReader.Move.FORWARD)
        assertEquals(ProductPageReader.Move.BACKWARD, step(r, quotes, forward = false).move)
        r.scrollFailed(ProductPageReader.Move.BACKWARD)
        val retry = step(r, quotes, forward = false)
        assertEquals(ProductPageReader.Move.BACKWARD, retry.move)
        assertEquals("", retry.result.draft)
        r.scrollSucceeded(ProductPageReader.Move.BACKWARD)
        val done = step(r, header)
        assertEquals(ProductPageReader.Move.FINISHED, done.move)
        assertTrue(done.result.draft.contains("Geld (Anzeige ungeprüft): 10,20"))
    }
    @Test fun persistentRejectedReturnDiscardsDraft() {
        val r = ProductPageReader(); step(r, header); step(r, quotes)
        repeat(3) {
            r.scrollFailed(ProductPageReader.Move.FORWARD)
            if (it < 2) assertEquals(ProductPageReader.Move.FORWARD, step(r, quotes).move)
        }
        repeat(3) {
            assertEquals(ProductPageReader.Move.BACKWARD, step(r, quotes).move)
            r.scrollFailed(ProductPageReader.Move.BACKWARD)
        }
        val aborted = step(r, quotes)
        assertEquals(ProductPageReader.Move.ABORT, aborted.move)
        assertEquals(ProductPageReader.Cause.RETURN_FAILED, aborted.cause)
        assertEquals("", aborted.result.draft)
    }
}
