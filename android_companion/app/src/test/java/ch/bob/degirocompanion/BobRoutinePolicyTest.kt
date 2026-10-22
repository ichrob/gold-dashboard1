package ch.bob.degirocompanion

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BobRoutinePolicyTest {
    @Test fun localUserCommandsAreExplicitlyAllowed() {
        assertTrue(BobRoutinePolicy.permits(BobRoutinePolicy.Action.OPEN_BOB, BobRoutinePolicy.Origin.USER_TAP))
        assertTrue(BobRoutinePolicy.permits(BobRoutinePolicy.Action.PICK_IMAGES, BobRoutinePolicy.Origin.USER_TAP))
        assertTrue(BobRoutinePolicy.permits(BobRoutinePolicy.Action.LOCAL_HEALTH_CHECK, BobRoutinePolicy.Origin.USER_TAP))
    }

    @Test fun scheduledTriggersAreFailClosed() {
        BobRoutinePolicy.Action.entries.forEach { action ->
            assertFalse(BobRoutinePolicy.permits(action, BobRoutinePolicy.Origin.SCHEDULE))
        }
        assertTrue(BobRoutinePolicy.permits(BobRoutinePolicy.Action.LOCAL_HEALTH_CHECK, BobRoutinePolicy.Origin.SCHEDULE, true))
        assertFalse(BobRoutinePolicy.permits(BobRoutinePolicy.Action.OPEN_BOB, BobRoutinePolicy.Origin.SCHEDULE, true))
        assertFalse(BobRoutinePolicy.permits(BobRoutinePolicy.Action.PICK_IMAGES, BobRoutinePolicy.Origin.SCHEDULE, true))
    }
}
