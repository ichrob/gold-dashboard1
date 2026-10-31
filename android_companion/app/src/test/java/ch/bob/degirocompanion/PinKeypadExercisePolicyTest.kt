package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class PinKeypadExercisePolicyTest {
    @Test fun deleteRequiresCompletionAndCannotRepeatOrResurrectAfterCancellation() {
        val p = PinKeypadExercisePolicy(); p.begin(true, true); p.digitCompleted(true)
        assertEquals(PinKeypadExercisePolicy.Action.DELETE, p.observe(true, true))
        repeat(3) {
            assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, false))
            assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, true))
        }
        p.deleteCompleted(true)
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, false))
        p.deleteCompleted(true)
        assertEquals(PinKeypadExercisePolicy.Action.FINISH, p.observe(true, false))
        repeat(3) { assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, true)) }
        for (cancel in listOf(true, false)) {
            val stopped = PinKeypadExercisePolicy(); stopped.begin(true, true); stopped.digitCompleted(true)
            stopped.observe(true, true)
            if (cancel) stopped.deleteCompleted(false) else stopped.stop()
            stopped.deleteCompleted(true); stopped.digitCompleted(true)
            repeat(3) {
                assertEquals(PinKeypadExercisePolicy.Action.NONE, stopped.observe(true, false))
                assertEquals(PinKeypadExercisePolicy.Action.NONE, stopped.observe(true, true))
                assertEquals(PinKeypadExercisePolicy.Action.NONE, stopped.begin(true, true))
            }
        }
    }

    @Test fun pendingAndCancelledTouchesCannotDeleteRepeatOrResurrect() {
        val pending = PinKeypadExercisePolicy()
        assertEquals(PinKeypadExercisePolicy.Action.DIGIT, pending.begin(true, true))
        repeat(3) {
            assertEquals(PinKeypadExercisePolicy.Action.NONE, pending.observe(true, true))
            assertEquals(PinKeypadExercisePolicy.Action.NONE, pending.begin(true, true))
        }
        pending.digitCompleted(true)
        assertEquals(PinKeypadExercisePolicy.Action.DELETE, pending.observe(true, true))
        pending.digitCompleted(true)
        assertEquals(PinKeypadExercisePolicy.Action.NONE, pending.observe(true, true))
        for (cancel in listOf(true, false)) {
            val stopped = PinKeypadExercisePolicy(); stopped.begin(true, true)
            if (cancel) stopped.digitCompleted(false) else stopped.stop()
            stopped.digitCompleted(true)
            assertEquals(PinKeypadExercisePolicy.Action.NONE, stopped.observe(true, true))
            assertEquals(PinKeypadExercisePolicy.Action.NONE, stopped.begin(true, true))
        }
    }

    @Test fun movementDoesNotRepeatActionsOrReusePriorDisabledSample() {
        val p = PinKeypadExercisePolicy()
        assertEquals(PinKeypadExercisePolicy.Action.DIGIT, p.begin(true, true))
        p.digitCompleted(true)
        assertEquals(PinKeypadExercisePolicy.Action.DELETE, p.observe(true, true))
        p.deleteCompleted(true)
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, false))
        p.pauseObservation()
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.begin(true, true))
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, false))
        assertEquals(PinKeypadExercisePolicy.Action.FINISH, p.observe(true, false))
    }
    @Test fun requiresConfirmationAndValidBaseline() {
        val p = PinKeypadExercisePolicy()
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.begin(false, true))
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.begin(true, false))
        assertFalse(p.issuedDigit)
    }
    @Test fun emitsOnlyOneDigitAndOneDeleteThenRequiresStableDisabledObservation() {
        val p = PinKeypadExercisePolicy()
        assertEquals(PinKeypadExercisePolicy.Action.DIGIT, p.begin(true, true))
        p.digitCompleted(true)
        repeat(5) { assertEquals(PinKeypadExercisePolicy.Action.NONE, p.begin(true, true)) }
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, false))
        assertEquals(PinKeypadExercisePolicy.Action.DELETE, p.observe(true, true))
        p.deleteCompleted(true)
        repeat(5) { assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, true)) }
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, false))
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, true))
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, false))
        assertEquals(PinKeypadExercisePolicy.Action.FINISH, p.observe(true, false))
        repeat(5) { assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, true)) }
    }
    @Test fun invalidationAndRejectedActionsCannotRestartOrDeleteLater() {
        for (afterDigit in listOf(false, true)) {
            val p = PinKeypadExercisePolicy()
            if (afterDigit) p.begin(true, true)
            p.observe(false, true)
            assertEquals(PinKeypadExercisePolicy.Action.NONE, p.begin(true, true))
            assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, true))
        }
        val p = PinKeypadExercisePolicy(); p.begin(true, true); p.stop()
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, true))
    }
}


