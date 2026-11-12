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
    @Test fun naturalScreenshotButtonNamesAndPressVerbsResolve() {
        for (text in listOf("drücke auf Schaltfläche Favoriten", "Bitte drücke auf die Schaltfläche Favoriten",
            "klicke auf den Button Favoriten", "Tippe auf den Reiter Favoriten", "druecke auf Favoriten")) {
            val steps = LocalWorkflow.parse(WorkflowMessage.resolve(text, listOf("Suche", "Favoriten"))!!)!!
            assertEquals(text, listOf(WorkflowStep(WorkflowAction.CLICK, "Favoriten", selectsTab=true)), steps)
        }
        assertEquals("Suche", WorkflowMessage.clickTarget("drücke auf Schaltfläche Suche", listOf("Suche")))
        assertNull(WorkflowMessage.resolve("drücke auf Favoriten und kaufe", listOf("Favoriten")))
        assertNull(WorkflowMessage.resolve("drücke nicht auf Favoriten", listOf("Favoriten")))
        assertNull(WorkflowMessage.resolve("drücke auf Favoriten", listOf("Suche")))
        assertNull(WorkflowMessage.resolve("drücke auf Schaltfläche Kaufen", listOf("Kaufen")))
        assertNull(WorkflowMessage.resolve("drücke auf Favoriten", listOf("Favoriten", "FAVORITEN")))
        assertEquals("Favoriten", LocalWorkflow.parse(WorkflowMessage.resolve(
            "Drücke auf Schaltfläche Favoriten und warte auf Meine Liste", listOf("Favoriten"))!!)!!.single().target)
    }
}
