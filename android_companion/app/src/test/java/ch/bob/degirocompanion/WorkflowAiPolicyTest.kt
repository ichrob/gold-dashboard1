package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowAiPolicyTest {
    private val nodes = listOf(WorkflowNode("", "search", true, true))
    @Test fun editableValuesAndPasswordsNeverBecomeCloudContext() {
        val safe = WorkflowAiPolicy.context(listOf(
            WorkflowNode("my private words", "search", true, true, inputValue="my private words"),
            WorkflowNode("Password", "password", true, false, password=true),
            WorkflowNode("Kontostand 100", "", false, false)))
        assertEquals(nodes, safe)
    }
    @Test fun proposalNeedsKnownTargetLiteralUserValueAndLocalGrammar() {
        val good = listOf(WorkflowStep(WorkflowAction.WRITE, "search", "Gold"))
        assertTrue(WorkflowAiPolicy.valid("Schreibe Gold", nodes, good))
        assertFalse(WorkflowAiPolicy.valid("Schreibe Gold", nodes, listOf(good[0].copy(value="Silver"))))
        assertFalse(WorkflowAiPolicy.valid("Schreibe Gold", nodes, listOf(good[0].copy(target="unknown"))))
        assertFalse(WorkflowAiPolicy.valid("Schreibe Gold", nodes, listOf(WorkflowStep(WorkflowAction.CLICK, "search", expected="Kaufen"))))
        assertFalse(WorkflowAiPolicy.valid("Schreibe Gold", nodes, listOf(WorkflowStep(WorkflowAction.CLICK, "search"))))
    }
    @Test fun failedOrJustStartedRunCannotEnterSuccessCache() {
        val steps = listOf(WorkflowStep(WorkflowAction.WAIT, "Gold"))
        val run = WorkflowRun("org.example.notes",steps,0)
        assertFalse(WorkflowAiPolicy.verified(run))
        run.stop("Abgebrochen")
        assertFalse(WorkflowAiPolicy.verified(run))
        val ok = WorkflowRun("org.example.notes",steps,0)
        ok.tick(WorkflowFrame("org.example.notes",1,listOf(WorkflowNode("Gold","",false,false))),1,true) { _, _ -> false }
        assertTrue(WorkflowAiPolicy.verified(ok))
    }
}
