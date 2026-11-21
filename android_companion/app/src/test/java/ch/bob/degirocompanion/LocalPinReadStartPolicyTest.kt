package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LocalPinReadStartPolicyTest {
    @Test fun onlyVerifiedUnlockedStoredPinCanStartAutomaticPinEntry() {
        assertTrue(LocalPinReadStartPolicy.useVerifiedPin(true,true,true))
        for(stored in listOf(false,true)) for(test in listOf(false,true))
            for(available in listOf(false,true)) {
                if(stored && test && available) continue
                assertFalse(LocalPinReadStartPolicy.useVerifiedPin(stored,test,available))
            }
    }
}
