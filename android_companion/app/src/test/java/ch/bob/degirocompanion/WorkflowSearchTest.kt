package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class WorkflowSearchTest {
    private val app = "org.example.notes"
    private val button = WorkflowNode("Suche","",false,true)
    private fun field(value: String="", id: String=app+":id/search_src_text") = WorkflowNode("Suchfeld",id,true,true,inputValue=value)
    private fun frame(vararg nodes: WorkflowNode) = WorkflowFrame(app,1,nodes.toList())
    @Test fun closedSearchNeedsNewUniqueFieldAndVerifiedWrite() {
        val initial=frame(button)
        val steps=WorkflowAuto.local("Schreibe Gold in das Suchfeld",initial)!!
        assertEquals(steps,LocalWorkflow.parse(WorkflowAiPolicy.commands(steps)))
        val run=WorkflowRun(app,steps,0)
        val actions=mutableListOf<WorkflowAction>()
        fun tick(f:WorkflowFrame,t:Long) { run.tick(f,t,true) { s, _ -> actions.add(s.action);true } }
        tick(initial,1);tick(initial,2)
        assertEquals(0,run.index)
        tick(frame(field()),3);assertEquals(1,run.index)
        tick(frame(field()),4);assertFalse(run.finished)
        tick(frame(field("Gold")),5)
        assertTrue(WorkflowAiPolicy.verified(run))
        assertEquals(listOf(WorkflowAction.CLICK,WorkflowAction.WRITE),actions)
    }
    @Test fun ambiguityAndMissingFieldNeverCauseRepeatedClicks() {
        assertNull(WorkflowAuto.local("Schreibe Gold in das Suchfeld",frame(button,button)))
        assertNull(WorkflowAuto.local("Schreibe Gold in das Suchfeld",frame(field(),field(id=app+":id/query"))))
        val run=WorkflowRun(app,WorkflowAuto.local("Schreibe Gold in das Suchfeld",frame(button))!!,0)
        var count=0
        for (time in listOf(1L,10L,1000L,20001L)) run.tick(frame(button),time,true) { _, _ -> count++;true }
        assertTrue(run.finished);assertEquals(1,count);assertFalse(WorkflowAiPolicy.verified(run))
    }
    @Test fun cloudCannotForgeLocalDynamicTargets() {
        val nodes=listOf(button,field())
        assertFalse(WorkflowAuto.autoPlan("Schreibe Gold",nodes,listOf(WorkflowStep(WorkflowAction.WRITE,WorkflowSearch.FIELD,"Gold"))))
        assertFalse(WorkflowAuto.autoPlan("Schreibe Gold",nodes,listOf(WorkflowStep(WorkflowAction.CLICK,"Suche",opensSearch=true))))
        assertNull(LocalWorkflow.parse("Öffne Suchfeld über \"Bestätigen\""))
    }
}
