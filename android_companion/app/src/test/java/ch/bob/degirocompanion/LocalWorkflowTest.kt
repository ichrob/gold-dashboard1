package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LocalWorkflowTest {
    private fun frame(vararg nodes: WorkflowNode) = WorkflowFrame("org.example.notes", 1, nodes.toList())
    private fun node(label: String, id: String = "", edit: Boolean = false, click: Boolean = false) = WorkflowNode(label, id, edit, click)
    @Test fun parsesWholeUserPlanAndRejectsMixedUnsafePlan() {
        assertEquals(3, LocalWorkflow.parse("Tippe auf \"Suche\" -> \"Suchbegriff\"\nSchreibe \"Gold\" in \"Suchbegriff\"\nWarte auf \"Gold\"")!!.size)
        assertNull(LocalWorkflow.parse("Warte auf \"Gold\"\nKaufe Gold"))
        assertNull(LocalWorkflow.parse("Tippe auf \"Kaufen\" -> \"Fertig\""))
        assertNull(LocalWorkflow.parse("Schreibe \"1234\" in \"PIN\""))
        assertNull(LocalWorkflow.parse("Tippe auf \"Suche\""))
    }
    @Test fun rejectsAmbiguityAndProtectedScreens() {
        val s = WorkflowStep(WorkflowAction.CLICK, "Suche", expected = "Treffer")
        assertNull(LocalWorkflow.target(s, frame(node("Suche", click=true), node("Suche", click=true))))
        assertNull(LocalWorkflow.target(s, frame(node("Suche", click=true), node("Anmelden"))))
        assertEquals(0, LocalWorkflow.target(s, frame(node("Suche", click=true))))
        assertFalse(LocalWorkflow.allowedApp("nl.degiro.trader"))
        assertFalse(LocalWorkflow.allowedApp("com.termux"))
    }
    @Test fun verifiesClickBeforeIssuingNextActionAndNeverRepeatsIt() {
        val plan = LocalWorkflow.parse("Tippe auf \"Suche\" -> \"Suchbegriff\"\nSchreibe \"Gold\" in \"Suchbegriff\"")!!
        val run = WorkflowRun("org.example.notes", plan, 0)
        var actions = 0
        val a = frame(node("Suche", click=true))
        run.tick(a, 1, true) { _, _ -> actions++; true }
        run.tick(a, 500, true) { _, _ -> actions++; true }
        assertEquals(1, actions); assertEquals(0, run.index)
        val b = frame(node("Suchbegriff", "search", edit=true))
        run.tick(b, 1000, true) { _, _ -> actions++; true }
        assertEquals(1, run.index)
        run.tick(b, 1500, true) { _, _ -> actions++; true }
        run.tick(frame(node("Gold", "wrong", edit=true)), 2000, true) { _, _ -> actions++; true }
        assertFalse(run.finished)
        run.tick(frame(node("Gold", "search", edit=true)), 2500, true) { _, _ -> actions++; true }
        assertTrue(run.finished); assertEquals(2, run.index); assertEquals(2, actions)
    }
    @Test fun timeoutAndLockNeverReportSuccess() {
        val p = listOf(WorkflowStep(WorkflowAction.WAIT, "Treffer"))
        val r = WorkflowRun("org.example.notes", p, 0)
        r.tick(null, 21_000, true) { _, _ -> fail(); false }
        assertTrue(r.finished); assertEquals(0, r.index)
        val locked = WorkflowRun("org.example.notes", p, 0)
        locked.tick(frame(node("Treffer")), 1, false) { _, _ -> fail(); false }
        assertEquals(0, locked.index)
    }
    @Test fun preexistingExpectationAndAppSwitchStop() {
        val s = WorkflowStep(WorkflowAction.CLICK, "Suche", expected="Treffer")
        val r = WorkflowRun("org.example.notes", listOf(s), 0)
        r.tick(frame(node("Suche", click=true), node("Treffer")), 1, true) { _, _ -> fail(); false }
        assertTrue(r.finished); assertEquals(0, r.index)
        val switched = WorkflowRun("org.example.notes", listOf(s), 0)
        switched.tick(frame(node("Suche", click=true)), 1, true) { _, _ -> true }
        switched.tick(WorkflowFrame("org.other", 2, emptyList()), 2, true) { _, _ -> fail(); false }
        assertTrue(switched.finished); assertEquals(0, switched.index)
    }
}
