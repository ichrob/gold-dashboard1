package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class BobWorkModePolicyTest {
    @Test fun onlyFourOrEightHoursAccepted() {
        assertEquals(14_400_000L, BobWorkModePolicy.duration(4))
        assertEquals(28_800_000L, BobWorkModePolicy.duration(8))
        assertThrows(IllegalArgumentException::class.java) { BobWorkModePolicy.duration(24) }
        assertEquals(0L, BobWorkModePolicy.remaining(1000, 1000, 12, 2000, 2000))
    }

    @Test fun windowExpiresWithoutExtendingAfterScreenOff() {
        val startWall = 1_700_000_000_000L
        val startElapsed = 2_000_000L
        assertEquals(14_400_000L,
            BobWorkModePolicy.remaining(startWall, startElapsed, 4, startWall, startElapsed))
        assertEquals(7_200_000L,
            BobWorkModePolicy.remaining(startWall, startElapsed, 4,
                startWall+7_200_000, startElapsed+7_200_000))
        assertEquals(0L,
            BobWorkModePolicy.remaining(startWall, startElapsed, 4,
                startWall+14_400_000, startElapsed+14_400_000))
    }

    @Test fun rebootOrClockChangesCannotExtendOwnerWindow() {
        val w=1_700_000_000_000L
        val e=10_000_000L
        assertEquals(0L, BobWorkModePolicy.remaining(w,e,8,w+100_000,10L))
        assertEquals(0L, BobWorkModePolicy.remaining(w,e,8,w-10L,e+1))
        assertEquals(0L, BobWorkModePolicy.remaining(w,e,8,w+400_000,e+100_000))
        assertEquals(0L, BobWorkModePolicy.remaining(w,e,8,w+100_000,e+400_000))
    }

    @Test fun readRequiresActiveWindowUnlockedInteractiveScreen() {
        assertTrue(BobWorkModePolicy.mayStartRead(1L,true,false))
        assertFalse(BobWorkModePolicy.mayStartRead(0L,true,false))
        assertFalse(BobWorkModePolicy.mayStartRead(1L,false,false))
        assertFalse(BobWorkModePolicy.mayStartRead(1L,true,true))
        assertEquals(900_000L, BobWorkModePolicy.MAX_READ_MILLIS)
    }
}
