package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class PinProbeHistoryTest {
    @Test fun flagsStayWithTheirObservationAndCannotLeakIntoAnotherRunOrView() {
        val history = PinProbeHistory()
        val flags = PinSymbolProbe.Flags(false, false, true, true, false)
        history.observe(PinProbePolicy.Result.SYMBOL_DISABLED, flags)
        history.observe(null)
        assertEquals(flags, history.symbolFlags)
        history.observe(PinProbePolicy.Result.SENSITIVE_INPUT)
        assertNull(history.symbolFlags)
        history.observe(PinProbePolicy.Result.SYMBOL_DISABLED, flags)
        history.clear()
        history.observe(null)
        assertNull(history.last)
        assertNull(history.symbolFlags)
    }
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

