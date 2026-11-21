package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LocalResearchForegroundPolicyTest {
    private fun allow(elapsed:Long, active:Boolean=true, unlocked:Boolean=true,
                      broker:Boolean=false) =
        LocalResearchForegroundPolicy.mayWait(elapsed,active,unlocked,broker)

    @Test fun ownerMayReturnFromChatBeforeFiveMinuteDeadline() {
        assertTrue(allow(0))
        assertTrue(allow(1500))
        assertTrue(allow(180_000))
        assertTrue(allow(LocalResearchForegroundPolicy.MAX_WAIT_MS-1))
        assertFalse(allow(LocalResearchForegroundPolicy.MAX_WAIT_MS))
        assertFalse(allow(LocalResearchForegroundPolicy.MAX_WAIT_MS+1))
        assertFalse(allow(-1))
        assertEquals(1500L,LocalResearchForegroundPolicy.POLL_MS)
    }

    @Test fun virtualizedGoldSearchMayWaitPassivelyButCannotExtendIndefinitely() {
        fun allow(elapsed:Long, active:Boolean=true, unlocked:Boolean=true,
                  broker:Boolean=true, readOnly:Boolean=true) =
            LocalResearchForegroundPolicy.mayWaitForVisibleSearch(
                elapsed,active,unlocked,broker,readOnly)
        assertTrue(allow(4_000L))
        assertTrue(allow(LocalResearchForegroundPolicy.MAX_VISIBLE_SEARCH_WAIT_MS-1))
        assertFalse(allow(LocalResearchForegroundPolicy.MAX_VISIBLE_SEARCH_WAIT_MS))
        assertFalse(allow(-1))
        assertFalse(allow(10_000L,active=false))
        assertFalse(allow(10_000L,unlocked=false))
        assertFalse(allow(10_000L,broker=false))
        assertFalse(allow(10_000L,readOnly=false))
    }

    @Test fun waitNeverAuthorizesALockedExpiredOrAlreadyVisibleBroker() {
        assertFalse(allow(1000,active=false))
        assertFalse(allow(1000,unlocked=false))
        assertFalse(allow(1000,broker=true))
        assertFalse(allow(LocalResearchForegroundPolicy.MAX_WAIT_MS,active=false))
    }
}
