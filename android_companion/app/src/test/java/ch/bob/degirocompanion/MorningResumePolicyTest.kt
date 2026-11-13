package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class MorningResumePolicyTest {
    @Test fun boundedFreshInterruptionsOnly() {
        assertTrue(MorningResumePolicy.eligible(1000,0,"SERVICE_INTERRUPTED"))
        assertTrue(MorningResumePolicy.eligible(900000,1,"SCREEN_LOCKED"))
        assertTrue(MorningResumePolicy.eligible(1000,0,"RETURN_NOT_CONFIRMED"))
        assertFalse(MorningResumePolicy.eligible(900001,0,"RETURN_NOT_CONFIRMED"))
        assertFalse(MorningResumePolicy.eligible(5000,2,"RETURN_NOT_CONFIRMED"))
        assertFalse(MorningResumePolicy.eligible(900001,0,"READ_TIMEOUT"))
        assertFalse(MorningResumePolicy.eligible(-1,0,"READ_TIMEOUT"))
        assertFalse(MorningResumePolicy.eligible(1000,2,"READ_TIMEOUT"))
        for(code in listOf("USER_STOP","PROTECTED_ORDER","PROTECTED_LOGIN","COMPLETE","PARTIAL"))
            assertFalse(MorningResumePolicy.eligible(1000,0,code))
    }
}
