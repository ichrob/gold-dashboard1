package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowOwnerLimitsTest {
    @Test fun ownerCanExtendRoutineWithoutChangingProtectedActionParser() {
        val plan = (1..24).joinToString("\n") { "Warte auf \"Ziel$it\"" }
        assertNull(LocalWorkflow.parse(plan))
        assertEquals(24, LocalWorkflow.parse(plan, 24)?.size)
        assertNull(LocalWorkflow.parse(plan, 23))
        assertNull(LocalWorkflow.parse("Tippe auf \"Kaufen\" -> \"Fertig\"", 48))
        assertNull(LocalWorkflow.parse("Schreibe \"1234\" in \"PIN\"", 48))
    }
    @Test fun selectedRunTimeoutsAreAppliedWithoutDisablingStopOrScreenProtection() {
        val limits = WorkflowOwnerLimits.bounded(24, 5, 40)
        val wait = listOf(WorkflowStep(WorkflowAction.WAIT, "Treffer"))
        val run = WorkflowRun("org.example.notes", wait, 0, limits)
        run.tick(null, 21_000, true) { _, _ -> false }
        assertFalse(run.finished)
        run.tick(null, 41_000, true) { _, _ -> false }
        assertTrue(run.finished)
        val overLimit = WorkflowRun("org.example.notes", List(25) { WorkflowStep(WorkflowAction.WAIT, "Treffer") }, 0, limits)
        assertTrue(overLimit.finished)
        overLimit.tick(null, 10, true) { _, _ -> fail("Oversized run executed"); false }
        val locked = WorkflowRun("org.example.notes", wait, 0, limits)
        locked.tick(null, 1, false) { _, _ -> false }
        assertTrue(locked.finished)
        val protected = WorkflowRun("org.example.notes", wait, 0, limits)
        protected.tick(WorkflowFrame("org.example.notes", 1,
            listOf(WorkflowNode("Passwort", "password", false, true))), 1, true) { _, _ ->
            fail("Protected action executed"); false
        }
        assertTrue(protected.finished)
        assertEquals(0, protected.index)
    }
    @Test fun demonstrationUsesOwnerStepCountButNeverChangesItsProtectedAppScope() {
        val demo = WorkflowDemonstration("org.example.notes", 24)
        repeat(24) { demo.write("field$it", "Gold") }
        assertEquals(24, demo.draft().size)
        assertEquals("", demo.error)
        demo.write("extra", "Silber")
        assertTrue(demo.error.contains("Schrittgrenze"))
        demo.observe(WorkflowFrame("org.example.notes",1,
            listOf(WorkflowNode("PIN", "pin", false, true))))
        assertEquals(24, demo.draft().size)
    }
    @Test fun corruptOrExcessiveSettingsAreClampedToFiniteBounds() {
        assertEquals(WorkflowOwnerLimits(), WorkflowOwnerLimits.bounded(12, 3, 20))
        assertEquals(WorkflowOwnerLimits(48, 15, 120), WorkflowOwnerLimits.bounded(1000, 1000, 1000))
        assertEquals(WorkflowOwnerLimits(1, 1, 10), WorkflowOwnerLimits.bounded(-1, -1, -1))
    }
}
