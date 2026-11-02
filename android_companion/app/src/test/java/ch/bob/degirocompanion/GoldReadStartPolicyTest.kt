package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class GoldReadStartPolicyTest {
    @Test fun pairedLocalStartCreatesMissingSession() {
        assertEquals(GoldReadStartPolicy.Decision.START_SESSION,
            GoldReadStartPolicy.decide(paired=true,sessionActive=false))
    }
    @Test fun existingActiveSessionIsReusedWithoutRestartingIt() {
        assertEquals(GoldReadStartPolicy.Decision.REUSE_SESSION,
            GoldReadStartPolicy.decide(paired=true,sessionActive=true))
    }
    @Test fun unpairedRunsCannotStartOrReuseAReadingSession() {
        for(active in listOf(false,true)) {
            assertEquals(GoldReadStartPolicy.Decision.BLOCK,
                GoldReadStartPolicy.decide(paired=false,sessionActive=active))
        }
    }
}
