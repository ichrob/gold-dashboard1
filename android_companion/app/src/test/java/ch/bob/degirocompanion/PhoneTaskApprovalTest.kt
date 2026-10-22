package ch.bob.degirocompanion

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneTaskApprovalTest {
    @Test fun permitsOnlyOnceAndRejectsReplay() {
        val gate = PhoneTaskApproval()
        gate.approve(PhoneTask.OPEN_BOB, 1000L)
        assertTrue(gate.consume(PhoneTask.OPEN_BOB, 1001L))
        assertFalse(gate.consume(PhoneTask.OPEN_BOB, 1002L))
    }

    @Test fun requiresTheSameTaskAndRejectsOtherActions() {
        val gate = PhoneTaskApproval()
        gate.approve(PhoneTask.OPEN_BOB, 1000L)
        assertFalse(gate.consume(PhoneTask.OPEN_SETTINGS, 1001L))
        assertFalse(gate.consume(PhoneTask.OPEN_BOB, 1002L))
    }

    @Test fun expiresAndRejectsClockRollback() {
        val gate = PhoneTaskApproval()
        gate.approve(PhoneTask.PICK_IMAGES, 10_000L)
        assertFalse(gate.consume(PhoneTask.PICK_IMAGES, 70_000L))
        gate.approve(PhoneTask.PICK_IMAGES, 10_000L)
        assertFalse(gate.consume(PhoneTask.PICK_IMAGES, 9_999L))
    }

    @Test fun clearRevokesApproval() {
        val gate = PhoneTaskApproval()
        gate.approve(PhoneTask.OPEN_BOB, 1000L)
        gate.clear()
        assertFalse(gate.consume(PhoneTask.OPEN_BOB, 1001L))
        gate.approve(PhoneTask.OPEN_BOB, 2000L)
        assertTrue(gate.consume(PhoneTask.OPEN_BOB, 2000L))
    }

    @Test fun unknownTaskCannotExecute() {
        val gate = PhoneTaskApproval()
        gate.approve(PhoneTask.OPEN_BOB, 1000L)
        assertFalse(gate.consume(null, 1001L))
        assertFalse(gate.consume(PhoneTask.OPEN_BOB, 1002L))
    }
}
