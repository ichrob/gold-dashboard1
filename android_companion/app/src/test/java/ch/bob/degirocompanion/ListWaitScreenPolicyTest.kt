package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ListWaitScreenPolicyTest {
    @Test fun onlyExplicitUnlockedInteractiveSessionCanBridgeReceiptWait() {
        for(active in listOf(false,true)) for(interactive in listOf(false,true))
            for(locked in listOf(false,true)) {
                val duration=ListWaitScreenPolicy.duration(active,interactive,locked)
                if(active && interactive && !locked) {
                    assertTrue(duration >= 100*5000L)
                    assertTrue(duration < 15*60*1000L)
                } else assertEquals(0L,duration)
            }
    }
}
