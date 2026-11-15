package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class RunOutboxTest {
    @Test fun currentReceiptSurvivesDeferredArchivesAndLateArchiveAck() {
        val initial=RunOutbox.checkpoint(mapOf(RunOutbox.CURRENT to "latest",
            "saved_run_1" to "old", "saved_run_2" to "older"),"latest")
        assertTrue(RunOutbox.currentPending(initial))
        assertFalse(RunOutbox.currentConfirmed(initial))
        assertNull(RunOutbox.acknowledge(initial,RunOutbox.CURRENT,"wrong",false))
        assertNull(RunOutbox.acknowledge(initial,RunOutbox.CURRENT,"latest",true))
        val confirmed=RunOutbox.acknowledge(initial,RunOutbox.CURRENT,"latest",false)!!
        assertTrue(RunOutbox.currentConfirmed(confirmed))
        assertFalse(RunOutbox.currentPending(confirmed))
        assertEquals(2,RunOutbox.archivedPending(confirmed))
        assertNotNull(RunOutbox.pendingKey(confirmed)) // legacy whole-outbox signal remains true
        val restarted=confirmed.toMap()
        val late=RunOutbox.acknowledge(restarted,"saved_run_1","old",false)!!
        assertTrue(RunOutbox.currentConfirmed(late))
        assertEquals(1,RunOutbox.archivedPending(late))
        val newer=RunOutbox.start(late,"new revision","saved_run_3")
        assertFalse(RunOutbox.currentConfirmed(newer))
        assertTrue(RunOutbox.currentPending(newer))
        assertFalse(RunOutbox.currentConfirmed(emptyMap()))
        assertFalse(RunOutbox.currentConfirmed(mapOf("saved_run_1" to "old")))
    }

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
        assertEquals(mapOf(RunOutbox.RESUME to "new"),RunOutbox.acknowledge(remaining,"saved_run_1","old",false))
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
        assertEquals(2,RunOutbox.candidateKeys(remaining).size)
        assertEquals("old list not owned",remaining["saved_run_1"])
    }

    @Test fun uploadedInterruptedRunSurvivesRestartWithoutRedelivery() {
        val saved=RunOutbox.checkpoint(mapOf("outbox" to "new partial revision 22",
            "saved_run_1" to "old completed report"),"new partial revision 22")
        val acknowledged=RunOutbox.acknowledge(saved,"outbox","new partial revision 22",false)!!
        // Simulate reloading the complete durable map after process death.
        val reloaded=acknowledged.toMap()
        assertEquals("new partial revision 22",RunOutbox.resumable(reloaded))
        assertEquals(listOf("saved_run_1"),RunOutbox.candidateKeys(reloaded))
        assertNull(RunOutbox.acknowledge(reloaded,RunOutbox.RESUME,"new partial revision 22",false))
        val resumed=RunOutbox.checkpoint(reloaded+(RunOutbox.CURRENT to "new partial revision 23"),
            "new partial revision 23")
        assertNull(RunOutbox.acknowledge(resumed,"outbox","new partial revision 22",false))
        assertNull(RunOutbox.acknowledge(resumed,"outbox","new partial revision 23",true))
        assertEquals("new partial revision 23",RunOutbox.resumable(resumed))
        assertEquals("old completed report",resumed["saved_run_1"])
    }

    @Test fun newCurrentWinsAndOldArchiveNeverBecomesResumeTarget() {
        assertNull(RunOutbox.resumable(mapOf("saved_run_1" to "old")))
        val old=mapOf(RunOutbox.RESUME to "previous acknowledged", "saved_run_1" to "old")
        val started=RunOutbox.checkpoint(RunOutbox.start(old,"latest","saved_run_2"),"latest")
        assertEquals("latest",RunOutbox.resumable(started))
        val ack=RunOutbox.acknowledge(started,"saved_run_1","old",false)!!
        assertEquals("latest",RunOutbox.resumable(ack))
        assertEquals(1,ack.keys.count { it == RunOutbox.RESUME })
    }

    @Test fun acknowledgementMigratesCurrentWithoutCheckpoint() {
        val migrated=RunOutbox.acknowledge(mapOf("outbox" to "partial"),"outbox","partial",false)!!
        assertEquals("partial",RunOutbox.resumable(migrated))
        assertNull(RunOutbox.pendingKey(migrated))
    }

    @Test(expected=IllegalArgumentException::class) fun archiveCollisionNeverOverwritesEvidence() {
        RunOutbox.start(mapOf("outbox" to "new","saved_run_1" to "old"),"next","saved_run_1")
    }
}
