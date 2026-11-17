package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class BobTradeDimPolicyTest {
    @Test fun requiresVerifiedOwnerSessionAndUnlockedInteractiveDevice() {
        assertTrue(BobTradeDimPolicy.eligible(true,0,true,false,true,true))
        assertFalse(BobTradeDimPolicy.eligible(false,0,true,false,true,true))
        assertFalse(BobTradeDimPolicy.eligible(true,0,false,false,true,true))
        assertFalse(BobTradeDimPolicy.eligible(true,0,true,true,true,true))
        assertFalse(BobTradeDimPolicy.eligible(true,0,true,false,false,true))
        assertFalse(BobTradeDimPolicy.eligible(true,0,true,false,true,false))
        assertFalse(BobTradeDimPolicy.eligible(true,BobTradeDimPolicy.MAX_OWNER_MILLIS,
            true,false,true,true))
        assertFalse(BobTradeDimPolicy.eligible(true,-1,true,false,true,true))
    }

    @Test fun tradeReceiptRequiresOneFreshIdenticalOpaqueIdentifier() {
        val token="a".repeat(24)
        assertTrue(BobTradeDimPolicy.validReceipt("ACTIVE",token,2_000L,2_000L))
        assertFalse(BobTradeDimPolicy.validReceipt("NO_ACTIVE",null,2_000L,2_000L))
        assertFalse(BobTradeDimPolicy.validReceipt("UNKNOWN",token,2_000L,2_000L))
        assertFalse(BobTradeDimPolicy.validReceipt("ACTIVE","private account",2_000L,2_000L))
        assertFalse(BobTradeDimPolicy.validReceipt("ACTIVE",token,1_939L,2_000L))
        assertFalse(BobTradeDimPolicy.validReceipt("ACTIVE",token,2_021L,2_000L))
        assertEquals(40_000L,BobTradeDimPolicy.SCREEN_LEASE_MILLIS)
        assertTrue(BobTradeDimPolicy.SCREEN_LEASE_MILLIS <
            BobTradeDimPolicy.MAX_OWNER_MILLIS)
    }
}
