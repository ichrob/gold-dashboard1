package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class WorkflowAppRouteTest {
    @Test fun degiroSelectableButNeverAllowedInGenericEngine() {
        assertTrue(WorkflowAppRoute.selectable("nl.degiro.trader"))
        assertFalse(LocalWorkflow.allowedApp("nl.degiro.trader"))
        assertFalse(WorkflowAppRoute.selectable("nl.degiro.trader.fake"))
        assertFalse(WorkflowAppRoute.selectable("com.android.settings"))
    }
    @Test fun onlyExplicitGoldReadingGoalsRouteToReader() {
        for (goal in listOf("Gold", "  Gold suchen  ", "Schreibe Gold in das Suchfeld", "Schreibe \"Gold\" in \"Suchfeld\""))
            assertTrue(goal,WorkflowAppRoute.goldRead(goal))
        for (goal in listOf("", "Gold kaufen", "Gold suchen und kaufen", "Schreibe Silber in das Suchfeld", "Anmelden", "Gold\nKaufen"))
            assertFalse(goal,WorkflowAppRoute.goldRead(goal))
    }
}
