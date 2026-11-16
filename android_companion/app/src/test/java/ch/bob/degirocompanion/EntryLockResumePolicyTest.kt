package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class EntryLockResumePolicyTest {
    @Test fun onlyOwnerOptedInIdleEntrySessionMayWait() {
        assertTrue(EntryLockResumePolicy.mayWaitForOwnerUnlock(true,true,true,false))
        for (a in listOf(false)) assertFalse(
            EntryLockResumePolicy.mayWaitForOwnerUnlock(a,true,true,false))
        assertFalse(EntryLockResumePolicy.mayWaitForOwnerUnlock(true,false,true,false))
        assertFalse(EntryLockResumePolicy.mayWaitForOwnerUnlock(true,true,false,false))
        assertFalse(EntryLockResumePolicy.mayWaitForOwnerUnlock(true,true,true,true))
    }

    @Test fun noResumptionWithoutUnexpiredSessionUnlockedDeviceAndBroker() {
        val good = EntryLockResumePolicy.mayResume(true,true,true,false,false,true)
        assertTrue(good)
        assertFalse(EntryLockResumePolicy.mayResume(false,true,true,false,false,true))
        assertFalse(EntryLockResumePolicy.mayResume(true,false,true,false,false,true))
        assertFalse(EntryLockResumePolicy.mayResume(true,true,false,false,false,true))
        assertFalse(EntryLockResumePolicy.mayResume(true,true,true,true,false,true))
        assertFalse(EntryLockResumePolicy.mayResume(true,true,true,false,true,true))
        assertFalse(EntryLockResumePolicy.mayResume(true,true,true,false,false,false))
    }
}
