package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowMessageTest {
    @Test fun imageAndTextProduceOneOwnerAuthoredPlan() {
        val plan = WorkflowMessage.resolve("Schreibe Silber 123,45 in Suchfeld", listOf("Suche", "Suchfeld"))!!
        assertEquals(WorkflowStep(WorkflowAction.WRITE, "Suchfeld", "Silber 123,45"), LocalWorkflow.parse(plan)!!.single())
    }
    @Test fun ambiguousReferenceNeedsOwnerSelection() {
        val text = "Schreibe 123 in dieses Feld"
        assertTrue(WorkflowMessage.needsTarget(text))
        assertNull(WorkflowMessage.resolve(text, listOf("Suche", "Suchfeld")))
        assertEquals("Suchfeld", LocalWorkflow.parse(WorkflowMessage.resolve(text, listOf("Suche", "Suchfeld"), "Suchfeld")!!)!!.single().target)
        assertNull(WorkflowMessage.resolve(text, listOf("Suche"), "Unknown"))
    }
    @Test fun plainClickCanAskForExpectedResultWithoutCommandSyntax() {
        assertEquals("Suche", WorkflowMessage.clickTarget("Tippe auf Suche", listOf("Suche", "Filter")))
        assertNull(WorkflowMessage.clickTarget("Tippe auf diese Schaltfläche", listOf("Suche", "Filter")))
        assertEquals("Filter", WorkflowMessage.clickTarget("Tippe auf diese Schaltfläche", listOf("Suche", "Filter"), "Filter"))
    }
    @Test fun screenshotIsNeverAnInstructionAndClicksNeedEvidence() {
        assertNull(WorkflowMessage.resolve("", listOf("Schreibe Gold in Suchfeld")))
        assertNull(WorkflowMessage.resolve("Tippe auf Suche", listOf("Suche")))
        assertNull(WorkflowMessage.resolve("Schreibe 20 in Kaufen", listOf("Kaufen")))
        assertNotNull(WorkflowMessage.resolve("Tippe auf diese Schaltfläche -> Suchfeld", listOf("Suche")))
        assertNull(WorkflowMessage.resolve("Schreibe Gold in Suchfeld", emptyList()))
    }
    @Test fun explicitSequenceCanReferToLaterScreen() {
        val text = "Tippe auf \"Suche\" -> \"Suchfeld\"\nSchreibe \"Silber\" in \"Suchfeld\""
        assertEquals(text, WorkflowMessage.resolve(text, listOf("Suche")))
        assertNull(WorkflowMessage.resolve(text, listOf("Andere Seite")))
    }
}
