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

    @Test fun linksAcceptOnlyExactSafeCommands() {
        assertTrue(BobRoutinePolicy.fromLink("bob-companion://command/open-bob") == BobRoutinePolicy.Action.OPEN_BOB)
        assertTrue(BobRoutinePolicy.fromLink("bob-companion://command/pick-images") == BobRoutinePolicy.Action.PICK_IMAGES)
        assertTrue(BobRoutinePolicy.fromLink("bob-companion://command/local-status") == BobRoutinePolicy.Action.LOCAL_HEALTH_CHECK)
        assertTrue(BobRoutinePolicy.fromLink("bob-companion://command/place-order") == null)
        assertTrue(BobRoutinePolicy.fromLink("bob-companion://command/open-bob?execute=true") == null)
        assertTrue(BobRoutinePolicy.fromLink("bob-companion://command/pick-images#payload") == null)
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
