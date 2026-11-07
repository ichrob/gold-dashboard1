package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class WorkflowAppRouteTest {
    @Test fun degiroAllowedButLookalikePackagesRemainBlocked() {
        assertTrue(WorkflowAppRoute.selectable("nl.degiro.trader"))
        assertTrue(LocalWorkflow.allowedApp("nl.degiro.trader"))
        assertFalse(WorkflowAppRoute.selectable("nl.degiro.trader.fake"))
        assertFalse(WorkflowAppRoute.selectable("com.android.settings"))
    }
    @Test fun onlyExplicitGoldReadingGoalsRouteToReader() {
        for (goal in listOf("Gold", "  Gold suchen  ", "Schreibe Gold in das Suchfeld", "Schreibe \"Gold\" in \"Suchfeld\""))
            assertTrue(goal,WorkflowAppRoute.goldRead(goal))
        for (goal in listOf("", "Gold kaufen", "Gold suchen und kaufen", "Schreibe Silber in das Suchfeld", "Anmelden", "Gold\nKaufen"))
            assertFalse(goal,WorkflowAppRoute.goldRead(goal))
    }
    @Test fun explicitLocalLoginRequestsIncludeOwnersNaturalSentence() {
        for (goal in listOf("öffne degiro und gebe selbstständig das Passwort ein zum Öffnen der App",
                "Öffne DEGIRO und gib die gespeicherte PIN ein.", "DEGIRO entsperren",
                "Melde mich bei DEGIRO an", "Starte die DEGIRO-App und gib automatisch die PIN ein")) {
            assertTrue(goal,WorkflowAppRoute.localLogin(goal))
            assertFalse(goal,WorkflowAppRoute.goldRead(goal))
        }
    }
    @Test fun loginRoutingRejectsSecretsAndAdditionalActions() {
        for (goal in listOf("", "öffne degiro", "Gold suchen", "Mein Passwort ist beispiel",
                "öffne degiro und gib die PIN 12345 ein", "DEGIRO entsperren und Gold kaufen",
                "DEGIRO entsperren\nGold suchen", "Öffne andere App und gib das Passwort ein",
                "nicht bei degiro anmelden", "DEGIRO entsperren und PIN löschen"))
            assertFalse(goal,WorkflowAppRoute.localLogin(goal))
    }
}
