package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class ReadNavigationStabilityTest {
    @Test fun waitsForStableTargetAndResetsAfterActionOrClockRollback() {
        val gate=ReadNavigationStability()
        assertFalse(gate.ready("window1:isinA:search",1000))
        assertFalse(gate.ready("window1:isinA:search",1399))
        assertTrue(gate.ready("window1:isinA:search",1400))
        assertFalse(gate.ready("window2:isinA:search",1500))
        assertFalse(gate.ready("window2:isinB:search",1600))
        assertTrue(gate.ready("window2:isinB:search",2000))
        gate.clear()
        assertFalse(gate.ready("window2:isinB:search",2001))
        assertFalse(gate.ready("window2:isinB:search",100))
    }
    @Test fun securityChallengesBlockWithoutAClick() {
        for(label in listOf("Two-factor authentication","Verification code","Fingerabdruck")) {
            val action=MorningReadPolicy.decide(listOf(MorningReadPolicy.Node(label)),"DE000FE11U69")
            assertEquals(MorningReadPolicy.Kind.BLOCK,action.kind)
            assertEquals("PROTECTED_LOGIN",action.code)
        }
    }
    @Test fun explicitChallengeUsesSpecificStopButGenericHeadingsDoNot() {
        for (label in listOf("Captcha", "Sicherheitsprüfung: Ich bin kein Roboter")) {
            val action=MorningReadPolicy.decide(listOf(MorningReadPolicy.Node(label)),"DE000FE11U69")
            assertEquals(MorningReadPolicy.Kind.BLOCK, action.kind)
            assertEquals("PROTECTED_VERIFICATION", action.code)
        }
        for (label in listOf("Sicherheitsprüfung", "Security Check")) {
            val action=MorningReadPolicy.discoverGold(listOf(MorningReadPolicy.Node(label)))
            assertFalse(action.code.startsWith("PROTECTED_"))
        }
    }
    @Test fun targetedIntentOnlySurvivesVerifiedLoginOnce() {
        LoginToReadHandoff.clear()
        val entry=SelectiveDetailPlan.Entry("DE000FE11U69",listOf("Geld","Brief","Anzeigezeit"))
        val refresh=LoginToReadHandoff.DetailRefresh("a".repeat(32),"2026-11-12T12:00:00Z",listOf(entry))
        LoginToReadHandoff.arm(1000,detailRefresh=refresh)
        assertEquals(refresh,LoginToReadHandoff.detailRefresh)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_ENTRY_SENT",1100))
        assertNull(LoginToReadHandoff.detailRefresh)
        LoginToReadHandoff.arm(2000,detailRefresh=refresh)
        assertTrue(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE",2200))
        assertNull(LoginToReadHandoff.detailRefresh)
    }
}
