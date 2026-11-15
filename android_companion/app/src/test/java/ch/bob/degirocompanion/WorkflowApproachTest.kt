package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class WorkflowApproachTest {
    private val frame = WorkflowFrame("org.bob.fixture", 1, listOf(WorkflowNode("Menü", "menu", false, true)))
    private val open = WorkflowStep(WorkflowAction.CLICK, "Menü", expected="Produkte")
    private val target = WorkflowStep(WorkflowAction.CLICK, "Produkte", expected="Suchfeld")
    @Test fun reachesMissingTargetThroughVerifiedNavigation() {
        assertEquals(listOf(open,target), WorkflowApproach.prepare(listOf(target),frame,listOf(listOf(open,target))))
        assertNull(WorkflowApproach.prepare(listOf(target),frame,emptyList()))
        assertEquals(listOf(open),WorkflowApproach.prepare(listOf(open),frame,emptyList()))
    }
    @Test fun verifiedTabNavigationCanPrecedeTheRequestedTarget() {
        val tab = WorkflowStep(WorkflowAction.CLICK,"Favoriten",selectsTab=true)
        val page = frame.copy(nodes=listOf(WorkflowNode("Favoriten","tab",false,true)))
        assertEquals(listOf(tab,target),WorkflowApproach.prepare(listOf(target),page,listOf(listOf(tab,target))))
    }
    @Test fun neverReplaysUnrelatedValuesOrChoosesAmbiguousRoute() {
        val write = WorkflowStep(WorkflowAction.WRITE,"Suchfeld","Gold")
        assertNull(WorkflowApproach.prepare(listOf(target),frame,listOf(listOf(open,write,target))))
        val alternate = open.copy(expected="Andere Ansicht")
        assertNull(WorkflowApproach.prepare(listOf(target),frame,listOf(listOf(open,target),listOf(alternate,target))))
        assertNull(WorkflowApproach.prepare(listOf(target),frame.copy(nodes=frame.nodes+WorkflowNode("PIN","",true,false,true)),listOf(listOf(open,target))))
    }
}
