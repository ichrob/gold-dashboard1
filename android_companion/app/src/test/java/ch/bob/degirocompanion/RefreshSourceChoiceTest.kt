package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class RefreshSourceChoiceTest {
    private val times = mapOf("old" to 1000L, "new" to 2000L, "same" to 2000L)

    @Test fun newerAcknowledgedRunWinsOverPinnedOlderBatch() {
        assertEquals("new", RefreshSourceChoice.choose("old", "new") { times[it] })
    }
    @Test fun invalidOrUnownedNewerCandidateCannotReplaceValidBatch() {
        assertEquals("old", RefreshSourceChoice.choose("old", "not-imported") { times[it] })
        assertEquals("new", RefreshSourceChoice.choose("not-imported", "new") { times[it] })
    }
    @Test fun noValidSourceNeverSilentlyFallsBackToUnverifiedData() {
        assertNull(RefreshSourceChoice.choose("bad", "also-bad") { times[it] })
        assertNull(RefreshSourceChoice.choose(null, null) { times[it] })
    }
    @Test fun oldOnlyStillReachesExistingFourteenHourExpiryGate() {
        // Choice is not an age waiver; ProductReadActivity enforces the same
        // <=14h check and the backend independently checks the original batch.
        assertEquals("old", RefreshSourceChoice.choose("old", null) { times[it] })
    }
}
