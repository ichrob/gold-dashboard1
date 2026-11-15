package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowProtectionSummaryTest {
    @Test fun onlyOwnerChosenNumbersAreListedAsFiveFixedRules() {
        assertEquals(listOf(2, 3, 5, 6, 7), WorkflowProtectionSummary.retained.keys.toList())
        assertEquals(listOf(1, 4, 8), WorkflowProtectionSummary.otherConditions.keys.toList())
        assertTrue(WorkflowProtectionSummary.retained.values.none { it.isBlank() })
    }

    @Test fun summaryNeverCreatesExecutionPermission() {
        assertNull(LocalWorkflow.parse("Tippe auf \"Kaufen\" -> \"Order\""))
        assertNull(LocalWorkflow.parse("Schreibe \"1234\" in \"PIN\""))
        assertTrue(LocalWorkflow.protected(WorkflowFrame("nl.degiro.trader", 1,
            listOf(WorkflowNode("Passwort", "password", false, true, password = true)))))
    }
}
