package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowReplayTest {
    @Test fun repeatingSearchUsesAnAlreadyOpenFieldWithItsExistingText() {
        val steps = listOf(WorkflowStep(WorkflowAction.CLICK,"Suche",expected="Suchfeld"),WorkflowStep(WorkflowAction.WRITE,"Suchfeld","Silber"))
        val frame = WorkflowFrame("org.fixture.app",1,listOf(WorkflowNode("Gold","org.fixture.app:id/search_src_text",true,true,inputValue="Gold")))
        assertEquals(listOf(WorkflowStep(WorkflowAction.WRITE,WorkflowSearch.FIELD,"Silber")),WorkflowReplay.prepare(steps,frame))
    }
    @Test fun missingOrAmbiguousSearchDoesNotSkipNavigation() {
        val steps = listOf(WorkflowStep(WorkflowAction.CLICK,"Suche",opensSearch=true),WorkflowStep(WorkflowAction.WRITE,WorkflowSearch.FIELD,"Gold"))
        val frame = WorkflowFrame("org.fixture.app",1,listOf(WorkflowNode("Suche","search",false,true)))
        assertEquals(steps,WorkflowReplay.prepare(steps,frame))
        val ambiguous = frame.copy(nodes=listOf(WorkflowNode("","search_src_text",true,true),WorkflowNode("","search_input",true,true)))
        assertEquals(steps,WorkflowReplay.prepare(steps,ambiguous))
    }
}
