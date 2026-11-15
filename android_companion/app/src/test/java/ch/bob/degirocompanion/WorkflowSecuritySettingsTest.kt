package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class WorkflowSecuritySettingsTest {
    @Test fun ownerCanEnableStricterReadOnlyAndLocalOnlyModes() {
        val standard = WorkflowSecurityPreferences()
        assertTrue(WorkflowSecuritySettings.permitsExecution(standard))
        assertTrue(WorkflowSecuritySettings.permitsCloud(standard))
        val strict = WorkflowSecurityPreferences(readOnlyWorkflows = true, offlineAiOnly = true)
        assertFalse(WorkflowSecuritySettings.permitsExecution(strict))
        assertFalse(WorkflowSecuritySettings.permitsCloud(strict))
        val localNavigation = strict.copy(readOnlyWorkflows = false)
        assertTrue(WorkflowSecuritySettings.permitsExecution(localNavigation))
        assertFalse(WorkflowSecuritySettings.permitsCloud(localNavigation))
    }

    @Test fun ownerPreferencesDoNotOverrideMandatoryProtection() {
        val standard = WorkflowSecurityPreferences()
        assertTrue(WorkflowSecuritySettings.permitsExecution(standard))
        assertNull(LocalWorkflow.parse("Tippe auf \"Kaufen\" -> \"Order\""))
        assertNull(LocalWorkflow.parse("Schreibe \"1234\" in \"PIN\""))
        val frame = WorkflowFrame("nl.degiro.trader", 1,
            listOf(WorkflowNode("Passwort", "password", false, true, password = true)))
        assertTrue(LocalWorkflow.protected(frame))
        assertNull(LocalWorkflow.target(WorkflowStep(WorkflowAction.CLICK,
            "Passwort", expected = "Ergebnis"), frame))
    }
}
