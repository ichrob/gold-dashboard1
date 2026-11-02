package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class DetailAutoRetryPolicyTest {
    @Test fun unchangedDeferredBatchIsBoundedButManualAndNewRunsStayEligible() {
        val t=1000000000L
        assertFalse(DetailAutoRetryPolicy.allowed("DEFERRED",t,true,t+1000))
        assertFalse(DetailAutoRetryPolicy.allowed("DEFERRED",t,true,t+
            DetailAutoRetryPolicy.DEFERRED_COOLDOWN_MS-1))
        assertTrue(DetailAutoRetryPolicy.allowed("DEFERRED",t,true,t+
            DetailAutoRetryPolicy.DEFERRED_COOLDOWN_MS))
        assertTrue(DetailAutoRetryPolicy.allowed("DEFERRED",t,false,t+1000))
        assertTrue(DetailAutoRetryPolicy.allowed("SAVED",t,true,t+1000))
        assertTrue(DetailAutoRetryPolicy.allowed("NOT_CONFIRMED",t,true,t+1000))
        assertTrue(DetailAutoRetryPolicy.allowed(null,t,true,t+1000))
        assertTrue(DetailAutoRetryPolicy.allowed("DEFERRED",0,true,t))
        assertTrue(DetailAutoRetryPolicy.allowed("DEFERRED",t,true,t-1000))
    }

    @Test fun localGenerationIsStableAndChangesForAddedOrRevisedReports() {
        val records=mapOf("saved_run_old" to "old values","outbox" to "current values")
        val hash=RunOutbox.generation(records)
        assertEquals(hash,RunOutbox.generation(records.toList().reversed().toMap()))
        assertEquals(64,hash.length)
        assertNotEquals(hash,RunOutbox.generation(records + ("outbox" to "new revision")))
        assertNotEquals(hash,RunOutbox.generation(records + ("saved_run_extra" to "new values")))
        assertNotEquals(hash,RunOutbox.generation(records - "saved_run_old"))
        assertNotEquals(hash,RunOutbox.generation(emptyMap()))
        assertFalse(hash.contains("current values"))
    }

    @Test fun anArchivedReportCannotBeDeletedByCheckingItsFingerprint() {
        val records=mapOf("saved_run_1" to "original evidence", "outbox" to "latest")
        val hash=RunOutbox.generation(records)
        assertEquals(2,records.size)
        assertEquals("original evidence",records["saved_run_1"])
        assertEquals(hash,RunOutbox.generation(records))
        assertNull(RunOutbox.acknowledge(records,"saved_run_1","wrong revision",false))
    }
}
