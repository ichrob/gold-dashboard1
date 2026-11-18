package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class PhoneDiagnosticPolicyTest {
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
