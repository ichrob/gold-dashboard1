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

    @Test fun ownerEntryReadModeIsolatedUntilVerifiedLocalPinLogin() {
        LoginToReadHandoff.clear()
        LoginToReadHandoff.arm(1000L, sessionOnly=true,
            entryReadOnly=true, resumeAfterOwnerUnlock=true)
        assertTrue(LoginToReadHandoff.pending(1500L))
        assertTrue(LoginToReadHandoff.sessionOnly)
        assertTrue(LoginToReadHandoff.entryReadOnly)
        assertTrue(LoginToReadHandoff.resumeAfterOwnerUnlock)
        assertNull(LoginToReadHandoff.searchQuery)
        assertNull(LoginToReadHandoff.detailRefresh)
        assertFalse(LoginToReadHandoff.freshGold)
        // PIN sent is NOT a verified logged-in broker market screen.
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_ENTRY_SENT",2000L))
        assertFalse(LoginToReadHandoff.entryReadOnly)
        assertFalse(LoginToReadHandoff.resumeAfterOwnerUnlock)
        LoginToReadHandoff.arm(3000L,sessionOnly=true,
            entryReadOnly=true,resumeAfterOwnerUnlock=true)
        assertTrue(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE",4000L))
        assertFalse(LoginToReadHandoff.sessionOnly)
        assertFalse(LoginToReadHandoff.entryReadOnly)
        assertFalse(LoginToReadHandoff.resumeAfterOwnerUnlock)
        LoginToReadHandoff.clear()
    }

    @Test fun unverifiedOrExpiredEntryReadNeverCarriesConsent() {
        for (failure in listOf("LOCAL_PIN_TIMEOUT","SCREEN_LOCKED",
                "LOCAL_PIN_DIALOG_BLOCKED","LOCAL_PIN_LAYOUT_CHANGED","USER_STOP")) {
            LoginToReadHandoff.clear()
            LoginToReadHandoff.arm(1000L,sessionOnly=true,
                entryReadOnly=true,resumeAfterOwnerUnlock=true)
            assertFalse(LoginToReadHandoff.consume(failure,2000L))
            assertFalse(LoginToReadHandoff.entryReadOnly)
            assertFalse(LoginToReadHandoff.resumeAfterOwnerUnlock)
        }
        LoginToReadHandoff.arm(1000L,sessionOnly=true,
            entryReadOnly=true,resumeAfterOwnerUnlock=true)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE",66000L))
        assertFalse(LoginToReadHandoff.entryReadOnly)
        assertFalse(LoginToReadHandoff.resumeAfterOwnerUnlock)
    }

    @Test fun entryReadCannotEscalateFullReaderOrOtherSession() {
        LoginToReadHandoff.clear()
        for (invalid in listOf<() -> Unit>(
                { LoginToReadHandoff.arm(1000L,entryReadOnly=true) },
                { LoginToReadHandoff.arm(1000L,resumeAfterOwnerUnlock=true) },
                { LoginToReadHandoff.arm(1000L,sessionOnly=true,
                    entryReadOnly=true,query="Gold") },
                { LoginToReadHandoff.arm(1000L,sessionOnly=true,
                    entryReadOnly=true,freshGold=true) })) {
            assertThrows(IllegalArgumentException::class.java) { invalid() }
            LoginToReadHandoff.clear()
        }
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

    @Test fun abortInvalidatesLateLoginAndImmediatelyReleasesNextTest() {
        LoginToReadHandoff.clear()
        LoginToReadHandoff.arm(1_000L,sessionOnly=true,
            entryReadOnly=true,resumeAfterOwnerUnlock=true)
        val oldTicket=LoginToReadHandoff.generation
        assertTrue(LoginToReadHandoff.pending(1_100L))
        LoginToReadHandoff.clear() // Explicit stop or screen-off abort.
        assertFalse(LoginToReadHandoff.pending(1_100L))
        assertNotEquals(oldTicket,LoginToReadHandoff.generation)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE",1_200L))
        assertFalse(LoginToReadHandoff.resumeAfterOwnerUnlock)
        // A new owner-initiated test may arm without waiting for old timeout.
        LoginToReadHandoff.arm(1_300L,sessionOnly=true,
            entryReadOnly=true,resumeAfterOwnerUnlock=true)
        assertTrue(LoginToReadHandoff.pending(1_400L))
        assertTrue(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE",1_400L))
        assertFalse(LoginToReadHandoff.pending(1_401L))
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
