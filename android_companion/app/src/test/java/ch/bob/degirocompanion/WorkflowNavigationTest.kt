package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowNavigationTest {
    private val step = WorkflowStep(WorkflowAction.CLICK,"Favoriten",selectsTab=true)
    private val frame = WorkflowFrame("org.bob.fixture",1,listOf(WorkflowNode("Favoriten","tab",false,true)))
    @Test fun selectionNeedsActualStateChangeAndOnlyOneClick() {
        val run = WorkflowRun(frame.app,listOf(step),0)
        var clicks = 0
        run.tick(frame,1,true) { _, _ -> clicks++; true }
        run.tick(frame.copy(window=2),2,true) { _, _ -> clicks++; true }
        assertFalse(run.finished)
        assertEquals(1,clicks)
        run.tick(frame.copy(nodes=frame.nodes.map { it.copy(selected=true) }),3,true) { _, _ -> clicks++; true }
        assertTrue(WorkflowAiPolicy.verified(run))
        assertEquals(1,clicks)
    }
    @Test fun alreadySelectedDoesNotToggleAndAmbiguousOrProtectedViewsDoNotClick() {
        val selected = WorkflowRun(frame.app,listOf(step),0)
        selected.tick(frame.copy(nodes=frame.nodes.map { it.copy(selected=true) }),1,true) { _, _ -> fail("Unnecessary click"); false }
        assertTrue(WorkflowAiPolicy.verified(selected))
        for (view in listOf(frame.copy(nodes=frame.nodes+frame.nodes),frame.copy(nodes=frame.nodes+WorkflowNode("Passwort","",false,false)))) {
            val run = WorkflowRun(frame.app,listOf(step),0)
            run.tick(view,1,true) { _, _ -> fail("Unsafe click"); false }
            assertFalse(WorkflowAiPolicy.verified(run))
        }
    }
    @Test fun unchangedViewTimesOutWithoutClaimingSuccess() {
        val run = WorkflowRun(frame.app,listOf(step),0)
        run.tick(frame,1,true) { _, _ -> true }
        run.tick(frame,21000,true) { _, _ -> fail("Repeated click"); false }
        assertTrue(run.finished)
        assertFalse(WorkflowAiPolicy.verified(run))
        assertNull(LocalWorkflow.parse("Wähle Register \"Kaufen\""))
        assertEquals(listOf(step),LocalWorkflow.parse(WorkflowAiPolicy.commands(listOf(step))))
    }
}
