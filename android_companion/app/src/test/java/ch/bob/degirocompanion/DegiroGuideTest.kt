package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class DegiroGuideTest {
    private fun frame(vararg nodes: WorkflowNode) = WorkflowFrame(WorkflowAppRoute.DEGIRO, 1, nodes.toList())
    @Test fun visibleNavigationIsNotEvidenceOfCurrentSection() {
        val tab = WorkflowNode("Favoriten", "tab", false, true)
        assertEquals("Ansicht noch nicht eindeutig erkannt", DegiroGuide.screen(frame(tab)))
        assertEquals("Register Favoriten · Auswahl erkannt", DegiroGuide.screen(frame(tab.copy(selected=true))))
        assertEquals("Ansicht noch nicht eindeutig erkannt", DegiroGuide.screen(frame(tab.copy(selected=true), WorkflowNode("Portfolio","portfolio",false,true,selected=true))))
    }
    @Test fun searchAndProtectionTakePrecedenceAndOldObservationsExpire() {
        val field = WorkflowNode("Suchfeld","search_field",true,true)
        val page = frame(field)
        assertEquals("Suche · Eingabefeld erkannt",DegiroGuide.screen(page))
        assertEquals("Mehrdeutige Suchansicht",DegiroGuide.screen(frame(field,field.copy(id="query"))))
        assertTrue(DegiroGuide.screen(frame(field,WorkflowNode("PIN","pin",true,true,true))).startsWith("Geschützte"))
        assertTrue(DegiroGuide.observation(page,60_001).contains("unbekannt"))
        assertTrue(DegiroGuide.observation(page,-1).contains("unbekannt"))
        assertTrue(DegiroGuide.observation(page,2_000).contains("vor 2 s"))
        assertTrue(DegiroGuide.observation(page.copy(app="org.other.app"),0).contains("unbekannt"))
    }
    @Test fun documentedSearchRouteRequiresUniqueLiveControlAndChecksOpening() {
        val page = frame(WorkflowNode("Suche","search_button",false,true))
        val write = WorkflowStep(WorkflowAction.WRITE, WorkflowSearch.FIELD, "Silber")
        val plan = WorkflowApproach.prepare(listOf(write),page,emptyList())!!
        assertEquals(2,plan.size)
        assertTrue(plan.first().opensSearch)
        assertEquals(write,plan.last())
        assertNull(DegiroGuide.approach(listOf(write),page.copy(nodes=page.nodes+page.nodes)))
        assertNull(DegiroGuide.approach(listOf(write),page.copy(app="org.other.app")))
        assertNull(DegiroGuide.approach(listOf(write.copy(target="Preis")),page))
        assertNull(DegiroGuide.approach(listOf(write.copy(value="Kaufen")),page))
    }
    @Test fun manualNeverCreatesBlindCoordinatesOrAuthorizesFinancialActions() {
        val write = WorkflowStep(WorkflowAction.WRITE,WorkflowSearch.FIELD,"Silber")
        assertNull(DegiroGuide.approach(listOf(write),frame(WorkflowNode("","icon",false,true))))
        assertNull(DegiroGuide.approach(listOf(write),frame(WorkflowNode("Suche","search",false,true),WorkflowNode("Kaufen","buy",false,true))))
        assertTrue(DegiroGuide.requested("DEGIRO-Anleitung"))
        assertFalse(DegiroGuide.requested("Kaufe ein Produkt"))
    }
}
