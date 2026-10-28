package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class PhoneDiagnosticPolicyTest {
    @Test fun onlyClosedErrorVocabularyCanLeaveDevice() {
        for(code in listOf("NONE","PROTECTED_PASSWORD","UNRECOGNIZED_INPUT","SEARCH_MISSING","SCREEN_LOCKED"))
            assertEquals(code,PhoneDiagnosticPolicy.code(code))
        for(text in listOf("account balance 1000","password secret","DE000FD0S0G4","https://example.com",""))
            assertEquals("OTHER",PhoneDiagnosticPolicy.code(text))
    }
}
