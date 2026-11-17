package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class TradeReadLeasePolicyTest {
    @Test fun renewBeforeEachFifteenMinuteSegmentWithoutTradeExpiry() {
        val segment=TradeReadLeasePolicy.SEGMENT_MILLIS
        assertEquals(900_000L,segment)
        val renewAt=segment-30_000L
        assertFalse(TradeReadLeasePolicy.renew(segment-renewAt+60_000L,true,true,false,false))
        assertTrue(TradeReadLeasePolicy.renew(segment-renewAt,true,true,false,false))
        // A confirmed trade continuing beyond 15 minutes can renew its
        // session repeatedly, without enlarging any individual session.
        var time=0L
        repeat(12) {
            time += renewAt
            assertTrue(TradeReadLeasePolicy.renew(segment-renewAt,true,true,false,false))
        }
        assertTrue(time>2*60*60*1000L)
    }
    @Test fun neverRenewWhenLockedUnverifiedOrReading() {
        assertFalse(TradeReadLeasePolicy.renew(30_000,false,true,false,false))
        assertFalse(TradeReadLeasePolicy.renew(30_000,true,false,false,false))
        assertFalse(TradeReadLeasePolicy.renew(30_000,true,true,true,false))
        assertFalse(TradeReadLeasePolicy.renew(30_000,true,true,false,true))
        assertFalse(TradeReadLeasePolicy.renew(0,true,true,false,false))
        assertFalse(TradeReadLeasePolicy.renew(600_000,true,true,false,false))
    }
    @Test fun ordinaryCompleteCanRemainIdleOnlyUnderVerifiedTrade() {
        assertTrue(TradeReadLeasePolicy.keepIdleAfterCompletedRead(true,"COMPLETE"))
        assertTrue(TradeReadLeasePolicy.keepIdleAfterCompletedRead(true,"COMPLETED"))
        for(code in listOf("USER_STOP","SCREEN_LOCKED","SESSION_EXPIRED",
                "PROTECTED_ORDER_CONFIRM","SERVICE_STOPPED","REMOTE_STOP")) {
            assertFalse(TradeReadLeasePolicy.keepIdleAfterCompletedRead(true,code))
        }
        assertFalse(TradeReadLeasePolicy.keepIdleAfterCompletedRead(false,"COMPLETE"))
    }
}
