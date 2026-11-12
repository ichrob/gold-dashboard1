package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LoginToReadHandoffTest {
    @Test fun freshGoldIntentSurvivesUntilVerifiedLoginAndCannotLeakToNextRun() {
        LoginToReadHandoff.clear()
        LoginToReadHandoff.arm(1000L, freshGold = true)
        assertTrue(LoginToReadHandoff.freshGold)
        assertTrue(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE", 2000L))
        assertFalse(LoginToReadHandoff.freshGold)
        LoginToReadHandoff.arm(3000L, freshGold = true)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_ENTRY_SENT", 4000L))
        assertFalse(LoginToReadHandoff.freshGold)
        LoginToReadHandoff.arm(5000L, freshGold = true)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE", 70000L))
        assertFalse(LoginToReadHandoff.freshGold)
        LoginToReadHandoff.arm(80000L)
        assertFalse(LoginToReadHandoff.freshGold)
        LoginToReadHandoff.clear()
    }

    @Test fun sessionOnlyIsOneShotAndNeverCarriesASearch() {
        LoginToReadHandoff.clear()
        LoginToReadHandoff.arm(1000L, sessionOnly = true)
        assertTrue(LoginToReadHandoff.sessionOnly)
        assertNull(LoginToReadHandoff.searchQuery)
        assertTrue(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE", 2000L))
        assertFalse(LoginToReadHandoff.sessionOnly)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE", 2001L))
        LoginToReadHandoff.arm(3000L)
        assertFalse(LoginToReadHandoff.sessionOnly)
        LoginToReadHandoff.clear()
    }

    @Test fun failedOrExpiredSessionOnlyLoginCannotProceed() {
        for (code in listOf("LOCAL_PIN_TIMEOUT", "SCREEN_LOCKED", "USER_STOP")) {
            LoginToReadHandoff.clear()
            LoginToReadHandoff.arm(1000L, sessionOnly = true)
            assertFalse(LoginToReadHandoff.consume(code, 2000L))
            assertFalse(LoginToReadHandoff.sessionOnly)
        }
        LoginToReadHandoff.arm(1000L, sessionOnly = true)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE", 66000L))
        assertFalse(LoginToReadHandoff.sessionOnly)
    }

    @Test fun onlyVerifiedMarketScreenCanStartProductReading() {
        LoginToReadHandoff.clear()
        LoginToReadHandoff.arm(1_000L)
        assertTrue(LoginToReadHandoff.pending(2_000L))
        assertTrue(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE", 2_000L))
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE", 2_001L))
    }

    @Test fun failedPinAndUnverifiedLoginNeverStartReading() {
        for (code in listOf("LOCAL_PIN_ENTRY_SENT", "LOCAL_PIN_RESULT_UNVERIFIED",
            "LOCAL_PIN_DIALOG_BLOCKED", "LOCAL_PIN_TIMEOUT", "SCREEN_LOCKED",
            "LOCAL_PIN_INTERRUPTED", "USER_STOP")) {
            LoginToReadHandoff.clear()
            LoginToReadHandoff.arm(1_000L)
            assertFalse(LoginToReadHandoff.consume(code, 2_000L))
            assertFalse(LoginToReadHandoff.pending(2_000L))
        }
    }

    @Test fun handoffExpiresAndCannotSurviveRollbackOrUnrelatedStop() {
        LoginToReadHandoff.clear()
        LoginToReadHandoff.arm(1_000L)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE", 66_001L))
        LoginToReadHandoff.arm(30_000L)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE", 29_999L))
        LoginToReadHandoff.arm(1_000L)
        LoginToReadHandoff.clear()
        assertFalse(LoginToReadHandoff.pending(1_001L))
    }
}
