package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class WorkflowAutoTest {
    private val app = "org.example.notes"
    private fun frame(vararg nodes: WorkflowNode) = WorkflowFrame(app, 1, nodes.toList())
    private fun field(id: String = "org.example.notes:id/search_src_text", value: String = "") =
        WorkflowNode(value, id, true, true, inputValue=value)

    @Test fun automaticCloudContextNeverIncludesPrivateValuesOrArbitraryLabels() {
        val nodes = WorkflowAuto.context(frame(field(value="private note"),
            WorkflowNode("Alice's note","org.example.notes:id/title",false,true),
            WorkflowNode("Suche","org.example.notes:id/arbitrary",false,true),
            WorkflowNode("Private", "org.example.notes:id/search", true,true,password=true)))
        // Entire protected screen yields no context, even alongside a valid search field.
        assertTrue(nodes.isEmpty())
        val safe = WorkflowAuto.context(frame(field(value="private note"),WorkflowNode("Alice's note","title",false,true),
            WorkflowNode("Suche","arbitrary",false,true)))
        assertEquals(2,safe.size)
        assertEquals("",safe[0].label);assertNull(safe[0].inputValue)
        assertEquals("Suche",safe[1].label);assertEquals("",safe[1].id)
    }
    @Test fun exactWriteUsesLocalFieldAndDoesNotNeedCloud() {
        val f = frame(field())
        val p = WorkflowAuto.local("Schreibe Gold in das Suchfeld",f)!!
        assertEquals("Gold",p.single().value)
        val run = WorkflowRun(app,p,0)
        var actions = 0
        run.tick(f,1,true) { _, _ -> actions++;true }
        assertFalse(WorkflowAiPolicy.verified(run))
        run.tick(frame(field(value="Gold")),2,true) { _, _ -> actions++;true }
        assertTrue(WorkflowAiPolicy.verified(run));assertEquals(1,actions)
        assertNull(WorkflowAuto.local("Schreibe Gold in das Suchfeld",frame(field(),field("org.example.notes:id/query"))))
    }
    @Test fun aiCannotIntroduceHiddenActionsOrUnrequestedInput() {
        val n = WorkflowAuto.context(frame(field(),WorkflowNode("Suche","",false,true)))
        assertFalse(WorkflowAuto.autoPlan("Finde meine Datei",n,listOf(WorkflowStep(WorkflowAction.WAIT,"Suche"))))
        assertTrue(WorkflowAuto.autoPlan("Schreibe Gold",n,listOf(WorkflowStep(WorkflowAction.WRITE,n[0].id,"Gold"))))
        assertFalse(WorkflowAuto.autoPlan("Schreibe Gold",n,listOf(WorkflowStep(WorkflowAction.WRITE,n[0].id,"Silver"))))
        assertFalse(WorkflowAuto.autoPlan("Schreibe Gold",n,listOf(WorkflowStep(WorkflowAction.CLICK,"Suche",expected="Bestätigen"))))
        assertFalse(WorkflowAuto.autoPlan("Schreibe Gold in die Suche",n,listOf(
            WorkflowStep(WorkflowAction.CLICK,"Suche",expected="Suchfeld"))))
        assertFalse(WorkflowAuto.autoPlan("Schreibe Gold",n,listOf(
            WorkflowStep(WorkflowAction.CLICK,"Suche",expected="Suchfeld"),
            WorkflowStep(WorkflowAction.WRITE,"Suchfeld","Gold"))))
    }
    @Test fun waitsForStableFrameAndAbortsOnLockAppSwitchOrTimeout() {
        val f = frame(field())
        val stable = WorkflowAutoObservation(app,0)
        assertNull(stable.next(f,1,true));assertNull(stable.next(f,500,true))
        assertEquals(f,stable.next(f,1001,true));assertNull(stable.next(f,1500,true))
        val changed = WorkflowAutoObservation(app,0)
        changed.next(f,1,true)
        changed.next(WorkflowFrame("org.other.app",2,emptyList()),2,true)
        assertTrue(changed.done);assertTrue(changed.reason.isNotBlank())
        val lock = WorkflowAutoObservation(app,0)
        assertNull(lock.next(f,1,false));assertTrue(lock.done)
        val timeout = WorkflowAutoObservation(app,0)
        assertNull(timeout.next(null,20_001,true));assertTrue(timeout.done)
    }
}
