package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class MorningReadUiPolicyTest {
    @Test fun stopRequiresOwnerConfirmationOnlyForActiveLocalOrRemoteWork() {
        val flags=List(7){false}
        assertFalse(MorningReadUiPolicy.stopConfirmationRequired(
            flags[0],flags[1],flags[2],flags[3],flags[4],flags[5],flags[6]))
        for(i in 0..6) {
            val active=flags.mapIndexed { j,value -> value || i==j }
            assertTrue(MorningReadUiPolicy.stopConfirmationRequired(
                active[0],active[1],active[2],active[3],active[4],active[5],active[6]))
        }
        assertEquals("Lesung durch ausdrücklich bestätigte Stopptaste beendet",
            MorningReadUiPolicy.reason("USER_STOP"))
        assertEquals("Lesung durch andere Bedienung unterbrochen",
            MorningReadUiPolicy.reason("USER_INTERRUPTED"))
    }
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
