package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class PinKeypadExerciseTraceTest {
    @Test fun interruptionRetainsLastAcceptedActionAndFirstCause() {
        for (stage in PinKeypadExerciseTrace.Stage.values()) {
            val trace = PinKeypadExerciseTrace()
            for (next in PinKeypadExerciseTrace.Stage.values().drop(1).take(stage.ordinal)) trace.advance(next)
            trace.end(PinKeypadExerciseTrace.Reason.TARGET_REFRESH_FAILED)
            trace.end(PinKeypadExerciseTrace.Reason.STOPPED)
            assertEquals(stage, trace.stage)
            assertEquals(PinKeypadExerciseTrace.Reason.TARGET_REFRESH_FAILED, trace.reason)
        }
    }
    @Test fun rejectedRequestIsNeverReportedAsAccepted() {
        val trace = PinKeypadExerciseTrace()
        trace.advance(PinKeypadExerciseTrace.Stage.DIGIT_REQUESTED)
        trace.end(PinKeypadExerciseTrace.Reason.DIGIT_REJECTED)
        assertEquals(PinKeypadExerciseTrace.Stage.DIGIT_REQUESTED, trace.stage)
        try { trace.advance(PinKeypadExerciseTrace.Stage.DIGIT_ACCEPTED); fail("Terminal trace advanced") }
        catch (_: IllegalStateException) {}
    }
    @Test(expected = IllegalStateException::class) fun acceptanceCannotSkipDispatch() {
        PinKeypadExerciseTrace().advance(PinKeypadExerciseTrace.Stage.DIGIT_ACCEPTED)
    }
}
