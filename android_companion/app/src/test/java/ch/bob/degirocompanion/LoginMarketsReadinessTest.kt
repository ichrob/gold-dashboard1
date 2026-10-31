package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LoginMarketsReadinessTest {
    private val markets = setOf("Märkte", "News", "Terminkalender",
        "Indizes", "Mit Namen, ISIN oder Symbol suchen")

    @Test fun onlyStableFocusedMarketsCanConfirmAndStartReader() {
        val gate=LoginMarketsReadiness()
        assertEquals(LoginMarketsReadiness.State.SETTLING,gate.observe(1000L,7,true,markets))
        assertEquals(LoginMarketsReadiness.State.SETTLING,gate.observe(1900L,7,true,markets))
        assertEquals(LoginMarketsReadiness.State.VERIFIED,gate.observe(2000L,7,true,markets))
        assertEquals(LoginMarketsReadiness.State.SETTLING,gate.observe(2100L,8,true,markets))
        assertEquals(LoginMarketsReadiness.State.VERIFIED,gate.observe(3100L,8,true,markets))
    }

    @Test fun blockedLoginOrMissingSearchCannotConfirmEvenWithMarketLabels() {
        val gate=LoginMarketsReadiness()
        val negatives=listOf("Haben Sie Ihren Code vergessen?", "PassCode",
            "Schließen", LoginDialogPolicy.NOTICE, LoginDialogPolicy.OFFER)
        assertEquals(LoginMarketsReadiness.State.ABSENT,
            gate.observe(1000L,1,true,markets - "Mit Namen, ISIN oder Symbol suchen"))
        for (marker in negatives) {
            assertEquals(LoginMarketsReadiness.State.ABSENT,
                gate.observe(2500L,1,true,markets+marker))
            assertEquals(LoginMarketsReadiness.State.SETTLING,
                gate.observe(2600L,1,true,markets))
        }
        assertEquals(LoginMarketsReadiness.State.ABSENT,gate.observe(4000L,1,false,markets))
        assertEquals(LoginMarketsReadiness.State.SETTLING,gate.observe(4100L,1,true,markets))
        assertEquals(LoginMarketsReadiness.State.SETTLING,gate.observe(4200L,1,true,markets))
    }

    @Test fun clockResetAndExplicitClearRequireNewWitness() {
        val gate=LoginMarketsReadiness()
        gate.observe(1000L,1,true,markets)
        assertEquals(LoginMarketsReadiness.State.SETTLING,gate.observe(900L,1,true,markets))
        gate.clear()
        assertEquals(LoginMarketsReadiness.State.SETTLING,gate.observe(2200L,1,true,markets))
        assertEquals(LoginMarketsReadiness.State.VERIFIED,gate.observe(3200L,1,true,markets))
    }
}
