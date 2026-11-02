package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class RunOutboxTest {
    @Test fun consecutiveStartsPreserveEveryUnacknowledgedRun() {
        val first=mapOf("outbox" to "first")
        val second=RunOutbox.start(first,"second","saved_run_1")
        val third=RunOutbox.start(second,"third","saved_run_2")
        assertEquals(mapOf("saved_run_1" to "first","saved_run_2" to "second","outbox" to "third"),third)
        assertEquals("outbox",RunOutbox.pendingKey(third))
    }
    @Test fun lateOldAcknowledgementCannotDeleteNewRunningResult() {
        val entries=mapOf("outbox" to "new revision","saved_run_1" to "old revision")
        assertEquals(mapOf("outbox" to "new revision"),RunOutbox.acknowledge(entries,"saved_run_1","old revision",true))
        assertNull(RunOutbox.acknowledge(entries,"outbox","old revision",false))
        assertNull(RunOutbox.acknowledge(entries,"outbox","new revision",true))
    }
    @Test fun backlogRemainsTransferableAfterCurrentAcknowledgement() {
        val entries=mapOf("outbox" to "new","saved_run_1" to "old")
        val remaining=RunOutbox.acknowledge(entries,"outbox","new",false)!!
        assertEquals("saved_run_1",RunOutbox.pendingKey(remaining))
        assertTrue(RunOutbox.acknowledge(remaining,"saved_run_1","old",false)!!.isEmpty())
        assertNull(RunOutbox.pendingKey(emptyMap()))
    }
    @Test fun abandonedHistoricalUploadDoesNotDeleteOrBlockNewerReport() {
        val original=mapOf("saved_run_1" to "old list not owned",
            "saved_run_2" to "older valid",
            "outbox" to "latest saved observations")
        assertEquals(listOf("outbox","saved_run_1","saved_run_2"),
            RunOutbox.candidateKeys(original))
        // The caller can defer an invalid linked batch during a single retry
        // and move to the next candidate without modifying persistent storage.
        val visited=mutableSetOf("outbox","saved_run_1")
        val next=RunOutbox.candidateKeys(original).first { it !in visited }
        assertEquals("saved_run_2",next)
        assertEquals(3,original.size)
        // Only a server-confirmed, exact copy may be removed.
        assertNull(RunOutbox.acknowledge(original,"saved_run_1","wrong evidence",false))
        assertEquals(3,original.size)
        val remaining=RunOutbox.acknowledge(original,"outbox","latest saved observations",false)!!
        assertEquals(2,remaining.size)
        assertEquals("old list not owned",remaining["saved_run_1"])
    }

    @Test(expected=IllegalArgumentException::class) fun archiveCollisionNeverOverwritesEvidence() {
        RunOutbox.start(mapOf("outbox" to "new","saved_run_1" to "old"),"next","saved_run_1")
    }
}
