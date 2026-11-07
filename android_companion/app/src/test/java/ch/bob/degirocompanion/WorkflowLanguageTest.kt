package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowLanguageTest {
    @Test fun naturalRequestsPreserveExactValuesAndMatchExistingActions() {
        for (text in listOf("Trage Silber 123,45 in Suchfeld ein", "Trage Silber 123,45 ins Suchfeld ein", "Gib Silber 123,45 in Suchfeld ein",
            "Setze Suchfeld auf Silber 123,45", "Kannst du bitte Silber 123,45 in Suchfeld eintragen?")) {
            assertEquals(text, listOf(WorkflowStep(WorkflowAction.WRITE,"Suchfeld","Silber 123,45")), LocalWorkflow.parse(text))
            assertTrue(WorkflowAiPolicy.sameGoal(text, "Schreibe Silber 123,45 in Suchfeld"))
        }
        assertFalse(WorkflowAiPolicy.sameGoal("Schreibe Gold in Suchfeld", "Schreibe gold in Suchfeld"))
        assertFalse(WorkflowAiPolicy.sameGoal("Schreibe 12,50 in Suchfeld", "Schreibe 1250 in Suchfeld"))
    }
    @Test fun favoritesVariantsUseTheSameCheckedSelection() {
        for (text in listOf("Öffne Favoriten", "Gehe zu Favoriten", "Wechsle zu Favoriten", "Zeige mir Favoriten",
            "Kannst du bitte die Favoriten öffnen?", "Könntest du auf die Schaltfläche Favoriten drücken?")) {
            val command = WorkflowMessage.resolve(text, listOf("Favoriten"))
            assertNotNull(text, command)
            assertTrue(text, LocalWorkflow.parse(command!!)!!.single().selectsTab)
        }
        assertNull(WorkflowMessage.resolve("Öffne Favoriten nicht", listOf("Favoriten")))
        assertNull(WorkflowMessage.resolve("Kannst du Favoriten oder Suche öffnen?", listOf("Favoriten","Suche")))
    }
    @Test fun degiroSynonymsKeepNativeLoginPrerequisites() {
        for (text in listOf("Finde Silber", "Such nach Silber", "Zeige mir Silber", "Bitte suche Silber"))
            assertEquals("Silber-Hebelprodukte suchen",WorkflowAppRoute.capability(text)?.title)
        assertEquals("DE000PM96QY2", DegiroGoal.productIsin("Bitte suche DE000PM96QY2"))
        assertNull(WorkflowAppRoute.capability("Finde Silber und kaufe"))
    }
    @Test fun textOnlyFavoritesAndAlternateWriteWorkLocally() {
        val frame = WorkflowFrame("org.bob.fixture",1,listOf(WorkflowNode("Favoriten","tab",false,true)))
        assertTrue(WorkflowAuto.local("Gehe zu Favoriten",frame)!!.single().selectsTab)
        val field = frame.copy(nodes=listOf(WorkflowNode("Suchfeld","search_input",true,true)))
        assertEquals("Silber 123,45",WorkflowAuto.local("Trage Silber 123,45 ins Suchfeld ein",field)!!.single().value)
    }
}
