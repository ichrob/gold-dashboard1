package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class PinKeypadPolicyTest {
    private fun keys(click: Boolean = true) = (0..9).map { PinKeypadPolicy.Key(it, click) }
    @Test fun requiresEveryDigit() {
        for (missing in 0..9) assertNull(PinKeypadPolicy.classify(keys().filter { it.digit != missing }))
    }
    @Test fun neverTreatsDuplicateDigitsAsUniqueTargets() {
        assertEquals(PinProbePolicy.Result.KEYPAD_AMBIGUOUS,
            PinKeypadPolicy.classify(keys() + PinKeypadPolicy.Key(0, true)))
    }
    @Test fun clickAvailabilityIsNotAnExecutedClick() {
        assertEquals(PinProbePolicy.Result.KEYPAD_CLICK_OFFERED, PinKeypadPolicy.classify(keys()))
        assertEquals(PinProbePolicy.Result.KEYPAD_VISIBLE, PinKeypadPolicy.classify(keys(false)))
        assertEquals(PinProbePolicy.Result.KEYPAD_VISIBLE,
            PinKeypadPolicy.classify(keys().map { if(it.digit == 5) it.copy(clickOffered=false) else it }))
    }
    @Test fun onlyExactSingleAsciiDigitsAreAccepted() {
        for (d in 0..9) assertEquals(d, PinKeypadPolicy.digit(d.toString()))
        for (s in listOf(null, "", "12", "12345", " 1", "1 ", "PIN 1", "•", "١"))
            assertNull(PinKeypadPolicy.digit(s))
    }
}
