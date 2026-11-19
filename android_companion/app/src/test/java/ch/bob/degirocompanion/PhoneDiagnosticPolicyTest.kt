package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class PhoneDiagnosticPolicyTest {
    @Test fun genericTurboNavigationCodesArePrivacySafeAndOwnerReadable() {
        for(code in listOf(
            "LIST_GENERIC_TURBO_UNFILTERED",
            "LIST_GENERIC_TURBO_START_BACK_SENT",
            "LIST_GENERIC_TURBO_RETURN_SENT",
            "LIST_GENERIC_TURBO_RETURN_FAILED",
            "LIST_GENERIC_TURBO_RETURN_STUCK",
            "LIST_GOLD_SEARCH_NOT_RESTORED",
            "LIST_GOLD_PREVIEW_DIRECT",
            "LIST_GOLD_PREVIEW_CAPTURE_FALLBACK",
            "LIST_ALL_RESULTS_LINK_UNSAFE")) {
            assertEquals(code,PhoneDiagnosticPolicy.code(code))
            assertNotEquals("OTHER",PhoneDiagnosticPolicy.code(code))
            assertFalse(MorningReadUiPolicy.reason(code).isBlank())
        }
        assertEquals("OTHER",PhoneDiagnosticPolicy.code(
            "278.459 Turbos und privates Konto 503,93 CHF"))
    }

    @Test fun localResearchHeartbeatNeverContainsProductIdentity() {
        assertEquals("LOCAL_RESEARCH_ACTIVE",
            PhoneDiagnosticPolicy.code("LOCAL_RESEARCH_ACTIVE"))
        assertFalse(MorningReadUiPolicy.reason("LOCAL_RESEARCH_ACTIVE").isBlank())
        assertEquals("OTHER",PhoneDiagnosticPolicy.code(
            "LOCAL_RESEARCH_ACTIVE DE000FD0S0G4 Geld 42 CHF"))
    }

    @Test fun onlyClosedErrorVocabularyCanLeaveDevice() {
        assertEquals("RETURN_NOT_CONFIRMED",PhoneDiagnosticPolicy.code("RETURN_NOT_CONFIRMED"))
        for(code in listOf("NONE","PROTECTED_ORDER_CONFIRM","PROTECTED_ORDER_TYPE","PROTECTED_ORDER_PRICE","PROTECTED_ORDER_QUANTITY","PROTECTED_PASSWORD","UNRECOGNIZED_INPUT","SEARCH_MISSING","SEARCH_TREE_EMPTY","SEARCH_NOT_ACTIONABLE","SCREEN_LOCKED"))
            assertEquals(code,PhoneDiagnosticPolicy.code(code))
        for(code in listOf("START_BUSY","START_SERVICE_NOT_READY","START_DIAGNOSTICS_UNPAIRED",
            "START_DEGIRO_MISSING","START_PIN_TEST_MISSING","START_PIN_UNAVAILABLE",
            "START_SESSION_FAILED","START_LAUNCH_FAILED","START_OTHER")) {
            assertEquals(code,PhoneDiagnosticPolicy.code(code))
            assertNotEquals("",MorningReadUiPolicy.reason(code))
        }
        for(text in listOf("account balance 1000","password secret","DE000FD0S0G4","https://example.com",""))
            assertEquals("OTHER",PhoneDiagnosticPolicy.code(text))
    }
}
