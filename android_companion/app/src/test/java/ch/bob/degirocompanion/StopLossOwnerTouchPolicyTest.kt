package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class StopLossOwnerTouchPolicyTest {
    private val own = "ch.bob.degirocompanion.stable"
    @Test fun ownerCanReachConsentScreenWithoutAccidentallyRevokingOrderDraft() {
        for(stage in listOf(StopLossPrefillPolicy.Stage.OPEN_FORM,
                StopLossPrefillPolicy.Stage.VERIFY_QUANTITY,
                StopLossPrefillPolicy.Stage.WAIT_OWNER,
                StopLossPrefillPolicy.Stage.SUBMIT_ORDER)) {
            assertFalse(StopLossOwnerTouchPolicy.mustAbort(stage,own,own))
        }
    }
    @Test fun outsideTouchAbortsActiveBrokerUiAutomations() {
        for(stage in listOf(StopLossPrefillPolicy.Stage.OPEN_FORM,
                StopLossPrefillPolicy.Stage.WRITE_STOP,
                StopLossPrefillPolicy.Stage.WRITE_QUANTITY,
                StopLossPrefillPolicy.Stage.SUBMIT_ORDER)) {
            assertTrue(StopLossOwnerTouchPolicy.mustAbort(stage,"nl.degiro.trader",own))
            assertTrue(StopLossOwnerTouchPolicy.mustAbort(stage,null,own))
            assertTrue(StopLossOwnerTouchPolicy.mustAbort(stage,"com.example.other",own))
        }
    }
    @Test fun passiveReviewDoesNotRevokeOwnerApproval() {
        assertFalse(StopLossOwnerTouchPolicy.mustAbort(
            StopLossPrefillPolicy.Stage.WAIT_OWNER,"nl.degiro.trader",own))
    }
}
