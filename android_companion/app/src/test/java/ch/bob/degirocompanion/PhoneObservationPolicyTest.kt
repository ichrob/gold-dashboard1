package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class PhoneObservationPolicyTest {
    @Test fun everyDetailedProtectionStillEndsTheSession() {
        for(code in listOf("PROTECTED_VIEW","PROTECTED_PASSWORD","PROTECTED_LOGIN","PROTECTED_ORDER_CONFIRM",
            "PROTECTED_ORDER_TYPE","PROTECTED_ORDER_PRICE","PROTECTED_ORDER_QUANTITY",
            "PROTECTED_SENSITIVE_CONTENT","PROTECTED_SENSITIVE_INPUT","UNRECOGNIZED_INPUT","INVALID_VIEW",
            "SCREEN_LOCKED","SERVICE_MISSING")) assertTrue(code,PhoneObservationPolicy.mustStop(code))
    }
    @Test fun productSearchAndOtherAppObservationsDoNotAcquireAStopMeaning() {
        for(code in listOf("SEARCH","QUERY","GOLD_IDENTITIES_MISSING","OTHER_APP","NO_ROOT"))
            assertFalse(code,PhoneObservationPolicy.mustStop(code))
    }
}
