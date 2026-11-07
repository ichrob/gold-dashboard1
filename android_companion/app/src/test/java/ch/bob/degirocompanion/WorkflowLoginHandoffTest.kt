package ch.bob.degirocompanion

import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class WorkflowLoginHandoffTest {
    @Before fun reset() = WorkflowLoginHandoff.clear()
    @After fun clean() = WorkflowLoginHandoff.clear()
    @Test fun taskWaitsForVerifiedLoginAndIsConsumedOnce() {
        var calls = 0
        WorkflowLoginHandoff.arm(100) { calls++ }
        assertEquals(0, calls)
        assertTrue(WorkflowLoginHandoff.pending(101))
        val next = WorkflowLoginHandoff.complete("LOCAL_PIN_HOME_VISIBLE", 200)
        assertNotNull(next)
        next!!()
        assertEquals(1, calls)
        assertNull(WorkflowLoginHandoff.complete("LOCAL_PIN_HOME_VISIBLE", 201))
    }
    @Test fun failuresExpiryAndStopNeverContinue() {
        for (code in listOf("LOCAL_PIN_TIMEOUT", "LOCAL_PIN_DIALOG_BLOCKED", "USER_STOP", "NO_WINDOW")) {
            WorkflowLoginHandoff.arm(100) { fail("Failed login must not execute a task") }
            assertNull(WorkflowLoginHandoff.complete(code, 200))
            assertFalse(WorkflowLoginHandoff.pending(201))
        }
        WorkflowLoginHandoff.arm(100) { fail("Expired login must not execute") }
        assertNull(WorkflowLoginHandoff.complete("LOCAL_PIN_HOME_VISIBLE", 65_100))
        WorkflowLoginHandoff.arm(100) { fail("Cancelled login must not execute") }
        WorkflowLoginHandoff.clear()
        assertNull(WorkflowLoginHandoff.complete("LOCAL_PIN_HOME_VISIBLE", 200))
    }
    @Test fun stopOrNewRequestInvalidatesAlreadyQueuedContinuation() {
        var calls = 0
        WorkflowLoginHandoff.arm(100) { calls++ }
        val next = WorkflowLoginHandoff.complete("LOCAL_PIN_HOME_VISIBLE", 200)!!
        val ticket = WorkflowLoginHandoff.generation
        WorkflowLoginHandoff.clear()
        WorkflowLoginHandoff.arm(300) { calls += 10 }
        if (ticket == WorkflowLoginHandoff.generation) next()
        assertEquals(0, calls)
        WorkflowLoginHandoff.complete("LOCAL_PIN_HOME_VISIBLE", 400)!!()
        assertEquals(10, calls)
    }
}
