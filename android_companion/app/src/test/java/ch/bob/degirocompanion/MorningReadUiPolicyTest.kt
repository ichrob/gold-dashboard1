package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class MorningReadUiPolicyTest {
    @Test fun mainButtonNeverStartsAnotherRunOrDiscardsPendingDiagnosis() {
        assertEquals(MorningReadUiPolicy.Action.OPEN,MorningReadUiPolicy.action(true,true,true,true))
        assertEquals(MorningReadUiPolicy.Action.SEND,MorningReadUiPolicy.action(false,true,false,false))
        assertEquals(MorningReadUiPolicy.Action.SETUP,MorningReadUiPolicy.action(false,false,true,false))
        assertEquals(MorningReadUiPolicy.Action.START,MorningReadUiPolicy.action(false,false,true,true))
    }
    @Test fun automaticTransmissionWaitsForUnlockAndRunsOnlyOncePerVersion() {
        assertTrue(MorningReadUiPolicy.automatic(true,true,false,true,false,"a:2","a:1"))
        assertFalse(MorningReadUiPolicy.automatic(true,true,false,true,false,"a:2","a:2"))
        assertFalse(MorningReadUiPolicy.automatic(true,true,true,true,false,"a:2",""))
        assertFalse(MorningReadUiPolicy.automatic(true,true,false,true,true,"a:2",""))
        assertFalse(MorningReadUiPolicy.automatic(true,true,false,false,false,"a:2",""))
        assertFalse(MorningReadUiPolicy.automatic(false,true,false,true,false,"a:2",""))
        assertFalse(MorningReadUiPolicy.automatic(true,false,false,true,false,"a:2",""))
    }
    @Test fun errorsHaveConcreteUserFacingReasons() {
        assertEquals("DEGIRO-Suche nicht erkannt",MorningReadUiPolicy.reason("SEARCH_MISSING"))
        assertEquals("Bildschirm wurde gesperrt",MorningReadUiPolicy.reason("SCREEN_LOCKED"))
    }
}
