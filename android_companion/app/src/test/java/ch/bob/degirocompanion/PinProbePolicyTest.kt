package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Test

class PinProbePolicyTest {
    private val field = PinProbePolicy.Field(true, true, true, true, true, false)
    @Test fun requiresOneEnabledNumericPasswordInput() {
        assertEquals(PinProbePolicy.Result.SET_TEXT_OFFERED, PinProbePolicy.classify(listOf(field), true))
        for (other in listOf(field.copy(password=false), field.copy(numeric=false), field.copy(enabled=false), field.copy(editable=false))) {
            assertEquals(PinProbePolicy.Result.INPUT_PRESENT, PinProbePolicy.classify(listOf(other), true))
        }
        assertEquals(PinProbePolicy.Result.NUMERIC_PASSWORD_INPUT, PinProbePolicy.classify(listOf(field.copy(setText=false)), true))
        assertEquals(PinProbePolicy.Result.NUMERIC_PASSWORD_INPUT, PinProbePolicy.classify(listOf(field,field), true))
    }
    @Test fun protectionAndIncompleteTreesNeverSuggestInput() {
        assertEquals(PinProbePolicy.Result.SENSITIVE_INPUT, PinProbePolicy.classify(listOf(field.copy(sensitive=true)), true))
        assertEquals(PinProbePolicy.Result.INCOMPLETE, PinProbePolicy.classify(listOf(field), false))
        assertEquals(PinProbePolicy.Result.NO_INPUT, PinProbePolicy.classify(emptyList(), true))
    }
}
