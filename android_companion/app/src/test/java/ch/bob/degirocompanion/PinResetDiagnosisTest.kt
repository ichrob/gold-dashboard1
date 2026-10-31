package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class PinResetDiagnosisTest {
    @Test fun absentKnownLabelIsNotClaimedToBeAnUnlabelledButton() {
        assertEquals(PinProbePolicy.Result.LOGIN_DELETE_LABEL_UNRECOGNIZED, PinResetEvidence().diagnosis())
    }
    @Test fun disabledLabelsDoNotOfferClicksOrProveEmptyInput() {
        val p=PinResetEvidence()
        p.observe(1, 0, true, false, false)
        assertEquals(0, p.count())
        assertEquals(PinProbePolicy.Result.LOGIN_DELETE_DISABLED, p.diagnosis())
    }
    @Test fun enabledLabelsWithoutNearbyActionHaveDistinctResult() {
        for (owner in listOf(null, 1)) {
            val p=PinResetEvidence()
            p.observe(owner, 3, true, false)
            assertEquals(PinProbePolicy.Result.LOGIN_DELETE_NO_ACTION, p.diagnosis())
        }
    }
    @Test fun mixedContainerAndMultipleTargetsAreDifferent() {
        val shared=PinResetEvidence()
        shared.observe(1, 0, true, false);shared.block(1)
        assertEquals(PinProbePolicy.Result.LOGIN_DELETE_SHARED_TARGET, shared.diagnosis())
        val multiple=PinResetEvidence()
        multiple.observe(1, 0, true, false);multiple.observe(2, 1, true, false)
        assertEquals(PinProbePolicy.Result.LOGIN_DELETE_AMBIGUOUS, multiple.diagnosis())
    }
    @Test fun oneUnblockedTargetRemainsOffered() {
        val p=PinResetEvidence()
        p.observe(1, 0, true, false);p.observe(1, 1, true, false)
        assertEquals(PinProbePolicy.Result.LOGIN_DELETE_OFFERED, p.diagnosis())
    }
    @Test fun funEnabledUnownedLabelOutranksDisabledLabel() {
        val p=PinResetEvidence()
        p.observe(null, 0, true, false, false)
        p.observe(null, 0, true, false, true)
        assertEquals(PinProbePolicy.Result.LOGIN_DELETE_NO_ACTION, p.diagnosis())
    }
}
