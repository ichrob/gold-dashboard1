package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowUsabilityTest {
    @Test fun revisesOnlyTheRequestedValueAndItsFollowingWait() {
        val steps = listOf(WorkflowStep(WorkflowAction.CLICK,"Suche",expected="Suchfeld"),
            WorkflowStep(WorkflowAction.WRITE,"Suchfeld","Gold"), WorkflowStep(WorkflowAction.WAIT,"Gold"))
        val revised = WorkflowRevision.apply("Nimm Silber statt Gold", steps)!!
        assertEquals(steps[0],revised[0]); assertEquals("Silber",revised[1].value); assertEquals("Silber",revised[2].target)
        assertEquals("123",WorkflowRevision.apply("Wiederhole das mit 123",steps)!![1].value)
        assertEquals(steps,WorkflowRevision.apply("Wiederhole das",steps))
        assertNull(WorkflowRevision.apply("Nimm Kaufen statt Gold",steps))
    }
    @Test fun ambiguousChangesRequireAnExplicitField() {
        val steps = listOf(WorkflowStep(WorkflowAction.WRITE,"A","Gold"),WorkflowStep(WorkflowAction.WRITE,"B","Gold"))
        assertNull(WorkflowRevision.apply("Nimm Silber statt Gold",steps))
        val result = WorkflowRevision.apply("Nimm Silber statt Gold",steps,1)!!
        assertEquals("Gold",result[0].value); assertEquals("Silber",result[1].value)
        assertNull(WorkflowRevision.apply("Nimm Silber statt Gold",steps,3))
    }
    @Test fun demonstrationCoalescesTypingAndInfersOnlyNewUnambiguousResults() {
        val demo = WorkflowDemonstration("org.fixture.app")
        val before = WorkflowFrame(demo.app,1,listOf(WorkflowNode("Suche","search",false,true)))
        demo.click("Suche",before)
        demo.observe(WorkflowFrame(demo.app,1,listOf(WorkflowNode("Suchfeld","query",true,true,inputValue=""))))
        demo.write("query","G"); demo.write("query","Go"); demo.write("query","Gold")
        assertEquals(2,demo.draft().size); assertEquals("Gold",demo.draft()[1].value)
        assertEquals("Suchfeld",demo.draft()[0].expected)
        demo.write("query",""); assertEquals("TEXT",demo.draft()[1].value)
    }
    @Test fun disappearingButtonCreatesAnExplicitlyUnreviewedStep() {
        val demo = WorkflowDemonstration("org.fixture.app")
        val before = WorkflowFrame(demo.app,1,listOf(WorkflowNode("Suche","search",false,true)))
        demo.observe(before)
        demo.observe(before.copy(nodes=listOf(WorkflowNode("Suchfeld","query",true,true,inputValue=""))))
        demo.write("query","Gold")
        assertEquals(2,demo.steps.size)
        assertEquals("ERGEBNISTEXT",demo.steps[0].expected)
        assertEquals("Gold",demo.steps[1].value)
    }
    @Test fun demonstrationKeepsUnknownResultsForOwnerReviewAndIsBounded() {
        val demo = WorkflowDemonstration("org.fixture.app")
        val frame = WorkflowFrame(demo.app,1,listOf(WorkflowNode("Suche","search",false,true)))
        demo.click("Suche",frame)
        demo.observe(frame.copy(nodes=listOf(WorkflowNode("A","",false,false),WorkflowNode("B","",false,false))))
        assertEquals("ERGEBNISTEXT",demo.draft()[0].expected)
        for (i in 1..20) demo.write("field$i","123")
        assertEquals(12,demo.draft().size); assertTrue(demo.error.isNotBlank())
    }
}
