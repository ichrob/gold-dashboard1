package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class WorkflowComposerTest {
    @Test fun screenshotLabelDoesNotBecomeAnInstruction() {
        assertNull(WorkflowComposer.command(WorkflowAction.CLICK, "Suche"))
        assertNull(WorkflowComposer.command(WorkflowAction.WRITE, "Suche", "Kaufen"))
        assertNull(WorkflowComposer.command(WorkflowAction.WAIT, "Suche\nKaufen"))
        assertNull(WorkflowComposer.command(WorkflowAction.WAIT, "\"Suche\""))
        assertNotNull(WorkflowComposer.command(WorkflowAction.CLICK, "Suche", expected="Suchbegriff"))
    }
    @Test fun sequenceFindsFutureFieldsAndVerifiesLettersAndNumbers() {
        val app = "nl.degiro.trader"
        val lines = listOf(
            WorkflowComposer.command(WorkflowAction.CLICK,"Suche",expected="Suchbegriff")!!,
            WorkflowComposer.command(WorkflowAction.WRITE,"Suchbegriff","Silber 123,45")!!,
            WorkflowComposer.command(WorkflowAction.WAIT,"Silber 123,45")!!)
        val first = WorkflowFrame(app,1,listOf(WorkflowNode("Suche","search",false,true)))
        val plan = WorkflowAuto.local(lines.joinToString("\n"),first)!!
        val run = WorkflowRun(app,plan,0)
        var issued = 0
        run.tick(first,1,true) { _, _ -> issued++; true }
        val field = WorkflowFrame(app,2,listOf(WorkflowNode("Suchbegriff","query",true,true,inputValue="")))
        run.tick(field,2,true) { _, _ -> fail("must only verify click");false }
        run.tick(field,3,true) { step, _ -> assertEquals("Silber 123,45",step.value);issued++;true }
        assertFalse(run.finished)
        val filled = WorkflowFrame(app,2,listOf(WorkflowNode("Silber 123,45","query",true,true,inputValue="Silber 123,45")))
        run.tick(filled,4,true) { _, _ -> fail("must only verify value");false }
        run.tick(filled,5,true) { _, _ -> fail("wait must not act");false }
        assertTrue(WorkflowAiPolicy.verified(run));assertEquals(2,issued)
    }
    @Test fun degiroStillStopsOnTradingScreen() {
        val step = WorkflowStep(WorkflowAction.WRITE,"Suche","Silber")
        val run = WorkflowRun("nl.degiro.trader",listOf(step),0)
        run.tick(WorkflowFrame("nl.degiro.trader",1,listOf(
            WorkflowNode("Suche","query",true,true), WorkflowNode("Kaufen","buy",false,true))),1,true) { _, _ -> fail("No trade-screen action");false }
        assertTrue(run.finished);assertEquals(0,run.index)
    }
}
