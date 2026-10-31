package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class PinKeypadExercisePolicyTest {
    @Test fun movementDoesNotRepeatActionsOrReusePriorDisabledSample() {
        val p = PinKeypadExercisePolicy()
        assertEquals(PinKeypadExercisePolicy.Action.DIGIT, p.begin(true, true))
        assertEquals(PinKeypadExercisePolicy.Action.DELETE, p.observe(true, true))
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
        repeat(5) { assertEquals(PinKeypadExercisePolicy.Action.NONE, p.begin(true, true)) }
        assertEquals(PinKeypadExercisePolicy.Action.NONE, p.observe(true, false))
        assertEquals(PinKeypadExercisePolicy.Action.DELETE, p.observe(true, true))
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
