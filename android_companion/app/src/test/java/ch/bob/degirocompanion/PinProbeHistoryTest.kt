package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class PinProbeHistoryTest {
    @Test fun appSwitchDoesNotEraseObservation() {
        val history = PinProbeHistory()
        history.observe(PinProbePolicy.Result.NO_INPUT)
        history.observe(null)
        history.observe(null)
        assertEquals(PinProbePolicy.Result.NO_INPUT, history.last)
    }
    @Test fun newRunCannotReuseOldEvidence() {
        val history = PinProbeHistory()
        history.observe(PinProbePolicy.Result.SET_TEXT_OFFERED)
        history.clear()
        history.observe(null)
        assertNull(history.last)
    }
    @Test fun newProtectedOrIncompleteObservationReplacesPriorHint() {
        val history = PinProbeHistory()
        history.observe(PinProbePolicy.Result.SET_TEXT_OFFERED)
        history.observe(PinProbePolicy.Result.SENSITIVE_INPUT)
        assertEquals(PinProbePolicy.Result.SENSITIVE_INPUT, history.last)
        history.observe(PinProbePolicy.Result.INCOMPLETE)
        assertEquals(PinProbePolicy.Result.INCOMPLETE, history.last)
    }
}
