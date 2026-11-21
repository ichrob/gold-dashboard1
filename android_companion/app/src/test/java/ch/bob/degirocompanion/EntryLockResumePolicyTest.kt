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
        // Point 4: an owner-started Gold product session may keep its IDLE
        // read-only ticket after screen-off, but cannot resume an active scan.
        assertTrue(EntryLockResumePolicy.mayWaitForOwnerUnlock(
            true,false,true,false,productReadOnly=true))
        assertFalse(EntryLockResumePolicy.mayWaitForOwnerUnlock(
            true,false,true,true,productReadOnly=true))
        assertFalse(EntryLockResumePolicy.mayWaitForOwnerUnlock(
            false,false,true,false,productReadOnly=true))
        assertFalse(EntryLockResumePolicy.mayWaitForOwnerUnlock(
            true,false,false,false,productReadOnly=true))
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
