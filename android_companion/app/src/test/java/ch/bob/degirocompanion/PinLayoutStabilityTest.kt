package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class PinLayoutStabilityTest {
    @Test fun requiresThreeEqualSamplesOverTwoSeconds() {
        val p = PinStableObservation<String>()
        assertFalse(p.observe("a", 0)); assertFalse(p.observe("a", 1000))
        assertTrue(p.observe("a", 2000))
        assertFalse(p.observe("b", 3000)); assertFalse(p.observe("b", 4000))
        assertTrue(p.observe("b", 5000))
    }
    @Test fun invalidWindowsGapsAndRepeatedClockReadingsCannotReuseStability() {
        val p = PinStableObservation<String>()
        p.observe("a", 0); p.observe("a", 1000)
        assertFalse(p.observe(null, 2000)); assertFalse(p.observe("a", 3000))
        assertFalse(p.observe("a", 6000)); assertFalse(p.observe("a", 6000))
        assertFalse(p.observe("a", 7000)); assertTrue(p.observe("a", 8000))
        p.clear(); assertFalse(p.observe("a", 9000))
    }
    @Test fun movedBoundsAreNeverPromotedEvenWhenStable() {
        val p = PinBoundsRecovery("original", 12000)
        assertEquals(PinBoundsRecovery.Decision.READY, p.observe("original", 0))
        for (time in 1000L..11000L step 1000)
            assertEquals(PinBoundsRecovery.Decision.WAIT, p.observe("moved", time))
        assertEquals(PinBoundsRecovery.Decision.EXPIRED, p.observe("moved", 12000))
        assertTrue(p.movementPending)
        assertEquals(PinBoundsRecovery.Decision.EXPIRED, p.observe("original", 13000))
    }
    @Test fun returnsOnlyAfterOriginalBoundsSettleAndCannotExtendDeadline() {
        val p = PinBoundsRecovery("original", 12000)
        p.observe("moved", 1000)
        assertEquals(PinBoundsRecovery.Decision.WAIT, p.observe("original", 2000))
        assertEquals(PinBoundsRecovery.Decision.WAIT, p.observe("original", 3000))
        assertEquals(PinBoundsRecovery.Decision.READY, p.observe("original", 4000))
        assertFalse(p.movementPending)
        assertEquals(PinBoundsRecovery.Decision.WAIT, p.observe("moved again", 11000))
        assertEquals(PinBoundsRecovery.Decision.EXPIRED, p.observe("original", 12000))
    }
}
