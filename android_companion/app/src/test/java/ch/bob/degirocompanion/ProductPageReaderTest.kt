package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductPageReaderTest {
    private val at = "2026-10-27T17:00:00Z"
    private fun lines(vararg text: String) = text.mapIndexed { i, v -> QuoteLayout.Line(v, 0, i * 50, 500, i * 50 + 30) }
    private val header = lines("DE000FD0S0G4", "EUR")
    private val quotes = lines("Geld EUR 10,20", "Brief EUR 10,30")
    private fun step(reader: ProductPageReader, data: List<QuoteLayout.Line>, forward: Boolean = true, backward: Boolean = true, window: Int = 1, sensitive: Boolean = false) = reader.inspect(window, data, at, sensitive, forward, backward)
    @Test fun missingKoCanCompleteWithoutQuoteAfterRealIdentityCheck() {
        val r=ProductPageReader()
        val detail=lines("DE000FD0S0G4 EUR",
            "SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10 LV 27.07")
        val done=r.inspect(1,detail,at,false,true,true,requireParameters=true,
            requestedTermsOnly=setOf("KO-Schwelle"))
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("KO-Schwelle (Anzeige ungeprüft): 3942"))
        assertFalse(done.result.draft.contains("Geld ("))
        assertFalse(r.anchored)
        val strict=ProductPageReader().inspect(1,detail,at,false,true,true,requireParameters=true)
        assertNotEquals(ProductPageReader.Move.FINISHED,strict.move)
    }
    @Test fun explicitlyRequestedUnpricedLeverageNeedsTheRealIsinAndStaysUnapproved() {
        val r=ProductPageReader()
        val terms=lines("DE000FE2JJ20","Hebel: 17,45","CHF 900 Account balance")
        val done=r.inspect(1,terms,at,false,true,true,requestedTermsOnly=setOf("Hebel"))
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("ISIN: DE000FE2JJ20"))
        assertTrue(done.result.draft.contains("Hebel (Anzeige ungeprüft): 17,45"))
        assertFalse(done.result.draft.contains("Währung (Anzeige ungeprüft): "))
        assertFalse(done.result.draft.contains("Geld ("))
        assertTrue(done.result.draft.contains("keine Order"))
        val strict=ProductPageReader().inspect(1,terms,at,false,true,true)
        assertNotEquals(ProductPageReader.Move.FINISHED,strict.move)
        val wrong=ProductPageReader().inspect(1,terms+lines("DE000FD0S0G4"),
            at,false,true,true,requestedTermsOnly=setOf("Hebel"))
        assertEquals(ProductPageReader.Move.ABORT,wrong.move)
        assertEquals(ProductPageReader.Cause.UNSAFE_VIEW,wrong.cause)
        assertEquals("",wrong.result.draft)
    }

    @Test fun aVisibleExactIsinCanFinishDespiteAmbiguousReturnScrollArea() {
        val r=ProductPageReader()
        assertEquals(ProductPageReader.Move.FORWARD,step(r,header).move)
        assertEquals(ProductPageReader.Move.BACKWARD,step(r,quotes).move)
        val done=r.inspect(1,header,at,false,true,true,scrollAmbiguous=true)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("ISIN: DE000FD0S0G4"))
        val protected=ProductPageReader()
        step(protected,header);step(protected,quotes)
        val rejected=protected.inspect(1,header+lines("Order bestätigen"),at,false,true,true,scrollAmbiguous=true)
        assertEquals(ProductPageReader.Cause.UNSAFE_VIEW,rejected.cause)
        assertEquals("",rejected.result.draft)
        val switched=ProductPageReader()
        step(switched,header);step(switched,quotes)
        val wrong=switched.inspect(1,lines("DE000FE2JJ20"),at,false,true,true,scrollAmbiguous=true)
        assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED,wrong.cause)
        assertEquals("",wrong.result.draft)
    }

    @Test fun requestedLeverageReadsPastTheQuotePairWithSameRealIsin() {
        val r=ProductPageReader()
        val first=lines("DE000FE2JJ20 CHF","Geld CHF 0,518","Brief CHF 0,528")
        val step=r.inspect(1,first,at,false,true,true,seekLeverage=true)
        assertEquals(ProductPageReader.Move.FORWARD,step.move)
        val second=lines("DE000FE2JJ20 CHF","Hebel: 17,45")
        val done=r.inspect(1,second,at,false,true,true,seekLeverage=true)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("Hebel (Anzeige ungeprüft): 17,45"))
        assertTrue(done.result.draft.contains("Geld (Anzeige ungeprüft): 0,518"))
        assertTrue(done.result.draft.contains("Brief (Anzeige ungeprüft): 0,528"))
    }

    @Test fun leverageCannotBorrowFromAnotherProductOrUnidentifiedSection() {
        val first=lines("DE000FE2JJ20 CHF","Geld CHF 0,518","Brief CHF 0,528")
        val r=ProductPageReader()
        r.inspect(1,first,at,false,true,true,seekLeverage=true)
        val wrong=r.inspect(1,lines("DE000FE6B3G9 CHF","Hebel: 99,99"),
            at,false,true,true,seekLeverage=true)
        assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED,wrong.cause)
        assertEquals("",wrong.result.draft)

        val safe=ProductPageReader()
        safe.inspect(1,first,at,false,true,true,seekLeverage=true)
        for(i in 1..3) safe.inspect(1,lines("Hebel: 99,99"),at,false,true,true,seekLeverage=true)
        val done=safe.inspect(1,first,at,false,true,true,seekLeverage=true)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertFalse(done.result.draft.contains("Hebel ("))
    }

    @Test fun morningReadSeeksMissingHeaderParametersAfterQuoteIdentity() {
        val r=ProductPageReader()
        val first=r.inspect(1,header+quotes,at,false,true,true,requireParameters=true)
        assertEquals(ProductPageReader.Move.BACKWARD,first.move)
        assertEquals("",first.result.draft)
        val title=lines("DE000FD0S0G4","SG Gold Turbo Unlimited Mini Call BAR","3942 BP 3901.07 Bv 10 LV 27.07")
        val done=r.inspect(1,title,at,false,true,true,requireParameters=true)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("Hebel (Anzeige ungeprüft): 27,07"))
        assertTrue(done.result.draft.contains("Geld (Anzeige ungeprüft): 10,20"))
    }
    @Test fun explicitlyPartialTitleDoesNotCauseRepeatedScrollingPastHeader() {
        val r=ProductPageReader()
        val title=lines("DE000FD0S0G4", "BNP GOLD Mini Long SL 3700 STR 3600 R 10")
        r.inspect(1,title,at,false,true,true,requireParameters=true)
        val back=r.inspect(1,quotes,at,false,true,true,requireParameters=true)
        assertEquals(ProductPageReader.Move.BACKWARD,back.move)
        val done=r.inspect(1,title,at,false,true,true,requireParameters=true)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("KO-Schwelle (Anzeige ungeprüft): 3700"))
        assertFalse(done.result.draft.contains("Hebel ("))
        assertFalse(done.result.draft.contains("Bv ("))
    }
    @Test fun completeQuotesReturnBeforeFooterEvenWhenForwardActionRemainsAvailable() {
        val r = ProductPageReader()
        step(r, header)
        val back = step(r, quotes, forward = true)
        assertEquals(ProductPageReader.Move.BACKWARD, back.move)
        assertEquals(ProductPageReader.Cause.QUOTES_CAPTURED, back.cause)
        assertEquals("", back.result.draft)
        r.scrollSucceeded(ProductPageReader.Move.BACKWARD)
        val done = step(r, header)
        assertEquals(ProductPageReader.Move.FINISHED, done.move)
        assertTrue(done.result.draft.contains("Brief (Anzeige ungeprüft): 10,30"))
    }
    @Test fun sameWindowRecheckStillRejectsProductChangeAndUnverifiedReturn() {
        val r = ProductPageReader()
        assertFalse(r.sameWindow(1))
        step(r, header)
        assertTrue(r.sameWindow(1))
        assertFalse(r.sameWindow(2))
        step(r, quotes)
        val changed = step(r, lines("DE000FE2JJ20"))
        assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED, changed.cause)
        assertEquals("", changed.result.draft)
        assertFalse(r.sameWindow(1))
        step(r, header)
        repeat(3) {
            val waiting = step(r, quotes, backward = false)
            assertEquals(ProductPageReader.Move.NONE, waiting.move)
            assertEquals(ProductPageReader.Cause.WAIT_SCROLL_LAYOUT, waiting.cause)
            assertEquals("", waiting.result.draft)
        }
        val noReturn = step(r, quotes, backward = false)
        assertEquals(ProductPageReader.Cause.RETURN_FAILED, noReturn.cause)
        assertEquals("", noReturn.result.draft)
    }
    @Test fun anchoredParametersSurviveQuoteSectionWithRepeatedIsin() {
        val r = ProductPageReader()
        val title = lines("DE000FD0S0G4", "SG Gold Turbo Unlimited Mini Call BAR", "3942 BP 3901.07 Bv 10 LV 27.07")
        step(r, title)
        val done = step(r, quotes + lines("Symbol | ISIN", "DE000FD0S0G4"))
        assertEquals(ProductPageReader.Move.FINISHED, done.move)
        assertTrue(done.result.draft.contains("KO-Schwelle (Anzeige ungeprüft): 3942"))
        assertTrue(done.result.draft.contains("Hebel (Anzeige ungeprüft): 27,07"))
        // No carried values may leak into another read after completion/reset.
        step(r, header)
        val clean = step(r, quotes + header)
        assertEquals(ProductPageReader.Move.FINISHED, clean.move)
        assertFalse(clean.result.draft.contains("KO-Schwelle"))
    }

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
        repeat(3) {
            val wait=step(r,quotes,forward=false,backward=false)
            assertEquals(ProductPageReader.Move.NONE,wait.move)
            assertEquals("",wait.result.draft)
        }
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
    @Test fun transientReturnSurfaceCanRecoverAfterOneSafeRetry() {
        val r=ProductPageReader()
        assertEquals(ProductPageReader.Move.FORWARD,step(r,header).move)
        val waiting=step(r,quotes,backward=false)
        assertEquals(ProductPageReader.Move.NONE,waiting.move)
        assertEquals(ProductPageReader.Cause.WAIT_SCROLL_LAYOUT,waiting.cause)
        assertEquals("",waiting.result.draft)
        val returned=step(r,quotes,forward=false,backward=true)
        assertEquals(ProductPageReader.Move.BACKWARD,returned.move)
        assertEquals("",returned.result.draft)
        val done=step(r,header)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("Geld (Anzeige ungeprüft): 10,20"))
    }

    @Test fun changedIdentityOrProtectedReturnStillFailsWithoutPublishing() {
        val r=ProductPageReader()
        step(r,header)
        assertEquals(ProductPageReader.Cause.WAIT_SCROLL_LAYOUT,
            step(r,quotes,backward=false).cause)
        val swapped=step(r,lines("DE000FE2JJ20","Geld EUR 10,20"))
        assertEquals(ProductPageReader.Move.ABORT,swapped.move)
        assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED,swapped.cause)
        assertEquals("",swapped.result.draft)
        val guard=ProductPageReader()
        step(guard,header)
        step(guard,quotes,backward=false)
        val protected=step(guard,lines("Ordertyp"),sensitive=true)
        assertEquals(ProductPageReader.Move.ABORT,protected.move)
        assertEquals("",protected.result.draft)
    }

    @Test fun persistentRejectedReturnDiscardsDraft() {
        val r = ProductPageReader(); step(r, header)
        val partial = lines("Zuletzt EUR 10,20")
        step(r, partial)
        repeat(3) {
            r.scrollFailed(ProductPageReader.Move.FORWARD)
            if (it < 2) assertEquals(ProductPageReader.Move.FORWARD, step(r, partial).move)
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

    @Test fun readsParametersFromSecondHeaderOnlyWithMatchingVisibleIsin() {
        val reader = ProductPageReader()
        val bare = lines("DE000FD0S0G4", "EUR")
        val detailed = lines("DE000FD0S0G4",
            "SG Gold Turbo Unlimited Mini Call BAR", "3942 BP 3901.07 Bv 10 LV 27.07")
        assertEquals(ProductPageReader.Move.FORWARD,
            reader.inspect(1, bare, at, false, true, true, requireParameters=true).move)
        assertEquals(ProductPageReader.Move.FORWARD,
            reader.inspect(1, detailed, at, false, true, true, requireParameters=true).move)
        val afterQuotes=reader.inspect(1, quotes, at, false, true, true, requireParameters=true)
        assertEquals(ProductPageReader.Move.BACKWARD, afterQuotes.move)
        assertEquals("", afterQuotes.result.draft)
        val done=reader.inspect(1, bare, at, false, true, true, requireParameters=true)
        assertEquals(ProductPageReader.Move.FINISHED, done.move)
        for(field in listOf("KO-Schwelle (Anzeige ungeprüft): 3942",
                "Basispreis (Anzeige ungeprüft): 3901,07", "Bv (Anzeige ungeprüft): 10",
                "Hebel (Anzeige ungeprüft): 27,07"))
            assertTrue("Missing $field", done.result.draft.contains(field))
    }

    @Test fun ignoresParametersWithoutVisibleIsinAndConflictingHeaders() {
        val bare = lines("DE000FD0S0G4", "EUR")
        val headerA = lines("DE000FD0S0G4", "SG Gold Turbo Unlimited Mini Call BAR",
            "3942 BP 3901.07 Bv 10 LV 27.07")
        val headerB = lines("DE000FD0S0G4", "SG Gold Turbo Unlimited Mini Call BAR",
            "3999 BP 3990.07 Bv 12 LV 30.07")
        val reader = ProductPageReader()
        reader.inspect(1, bare, at, false, true, true, requireParameters=true)
        reader.inspect(1, headerA, at, false, true, true, requireParameters=true)
        reader.inspect(1, headerB, at, false, true, true, requireParameters=true)
        reader.inspect(1, quotes, at, false, true, true, requireParameters=true)
        val done=reader.inspect(1, bare, at, false, true, true, requireParameters=true)
        assertEquals(ProductPageReader.Move.FINISHED, done.move)
        assertTrue(done.result.draft.contains("KO-Schwelle (Anzeige ungeprüft): 3942"))
        assertFalse(done.result.draft.contains("3999"))

        val unpaired = ProductPageReader()
        unpaired.inspect(1, bare, at, false, true, true, requireParameters=true)
        unpaired.inspect(1, headerA.drop(1), at, false, true, true, requireParameters=true)
        unpaired.inspect(1, quotes, at, false, true, true, requireParameters=true)
        val safe=unpaired.inspect(1, bare, at, false, true, true, requireParameters=true)
        assertEquals(ProductPageReader.Move.BACKWARD, safe.move)
        assertEquals("", safe.result.draft)
    }

    @Test fun aLaterPartialScreenDoesNotEraseARecordedQuoteLabel() {
        val reader=ProductPageReader()
        assertEquals(ProductPageReader.Move.FORWARD,step(reader,header).move)
        assertEquals(ProductPageReader.Move.FORWARD,step(reader,lines("Zuletzt EUR 10,20")).move)
        assertEquals(ProductPageReader.Move.FORWARD,step(reader,lines("Geld EUR 10,15")).move)
        assertEquals(ProductPageReader.Move.BACKWARD,step(reader,lines("Notizen","Notiz hinzufügen")).move)
        val done=step(reader,header)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("Zuletzt (Anzeige ungeprüft): 10,20"))
        assertFalse(done.result.draft.contains("Geld (Anzeige ungeprüft): 10,15"))
    }

    @Test fun matchingBidAskPairStillUpgradesEarlierSingleQuote() {
        val reader=ProductPageReader()
        assertEquals(ProductPageReader.Move.FORWARD,step(reader,header).move)
        assertEquals(ProductPageReader.Move.FORWARD,step(reader,lines("Zuletzt EUR 10,20")).move)
        assertEquals(ProductPageReader.Move.BACKWARD,step(reader,quotes).move)
        val done=step(reader,header)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("Geld (Anzeige ungeprüft): 10,20"))
        assertTrue(done.result.draft.contains("Brief (Anzeige ungeprüft): 10,30"))
    }
}
