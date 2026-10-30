package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class PinLoginEvidenceTest {
    private val keys = PinProbePolicy.Result.KEYPAD_CLICK_OFFERED
    @Test fun keypadAloneNeverIdentifiesLogin() {
        assertEquals(keys, PinLoginEvidence.classify(keys, false, false, 1))
    }
    @Test fun requiresUniqueDeleteTarget() {
        for (count in listOf(0, 2, 10))
            assertEquals(PinProbePolicy.Result.LOGIN_RESET_UNCONFIRMED,
                PinLoginEvidence.classify(keys, true, false, count))
        assertEquals(PinProbePolicy.Result.LOGIN_DELETE_OFFERED,
            PinLoginEvidence.classify(keys, true, false, 1))
    }
    @Test fun setupDialogAlwaysBlocksLoginClassification() {
        assertEquals(PinProbePolicy.Result.LOGIN_SETUP_VISIBLE,
            PinLoginEvidence.classify(keys, true, true, 1))
    }
    @Test fun incompleteOrAmbiguousKeysCannotBePromoted() {
        for (state in listOf(PinProbePolicy.Result.KEYPAD_VISIBLE, PinProbePolicy.Result.KEYPAD_AMBIGUOUS,
            PinProbePolicy.Result.INCOMPLETE, PinProbePolicy.Result.SENSITIVE_INPUT))
            assertEquals(state, PinLoginEvidence.classify(state, true, false, 1))
    }
    @Test fun matchesOnlyExactFixedLabels() {
        assertEquals(PinLoginEvidence.Marker.LOGIN_HELP,
            PinLoginEvidence.marker("Haben Sie Ihren Code vergessen?"))
        assertEquals(PinLoginEvidence.Marker.DELETE_KEY, PinLoginEvidence.marker("Backspace"))
        for (value in listOf(null, "", "12345", "Konto löschen", "Order löschen", "Code", "Schließen"))
            assertEquals(PinLoginEvidence.Marker.NONE, PinLoginEvidence.marker(value))
    }
}
