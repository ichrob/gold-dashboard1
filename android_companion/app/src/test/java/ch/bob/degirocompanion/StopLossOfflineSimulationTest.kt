package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class StopLossOfflineSimulationTest {
    @Test fun acceptedOfflineFormSimulatesTwoValuesButNeverSubmits() {
        val r=StopLossOfflineSimulation.run(StopLossOfflineSimulation.Scenario.HAPPY_PATH)
        assertTrue(r.reason+" "+r.trace.joinToString("; "),r.passed)
        assertEquals("25,90",r.stopText)
        assertEquals("3",r.quantityText)
        assertFalse(r.brokerOpened)
        assertFalse(r.orderSubmitted)
        assertTrue(r.trace.any { it.contains("Stop Loss") })
        assertTrue(r.trace.any { it.contains("Werte kontrolliert") })
    }
    @Test fun wrongIsinIsBlockedBeforeAnyFieldChanges() {
        val r=StopLossOfflineSimulation.run(StopLossOfflineSimulation.Scenario.WRONG_ISIN)
        assertTrue(r.trace.joinToString("; "),r.passed)
        assertEquals("",r.stopText)
        assertEquals("",r.quantityText)
        assertTrue(r.trace.any { it.contains("PRODUKT_ISIN_NICHT_ERKANNT") })
    }
    @Test fun buyMaskIsNeverTreatedAsSell() {
        val r=StopLossOfflineSimulation.run(StopLossOfflineSimulation.Scenario.BUY_SELECTED)
        assertTrue(r.trace.joinToString("; "),r.passed)
        assertEquals("",r.stopText)
        assertEquals("",r.quantityText)
        assertTrue(r.trace.any { it.contains("VERKAUF_NICHT_BESTAETIGT") })
    }
    @Test fun ambiguousFieldStopsWithoutWriting() {
        val r=StopLossOfflineSimulation.run(StopLossOfflineSimulation.Scenario.AMBIGUOUS_STOP_FIELD)
        assertTrue(r.trace.joinToString("; "),r.passed)
        assertEquals("",r.stopText)
        assertEquals("",r.quantityText)
        assertTrue(r.trace.any { it.contains("STOP_FELD_NICHT_EINDEUTIG") })
    }
    @Test fun freshBobModelDraftDrivesAllFourScenariosWithoutBroker() {
        val now=1_800_000_000_000L
        val raw="BOB-STOP/1|DE000PM96QY2|EUR|7|12.43|$now"
        val model=StopLossOfflineSimulation.modelDraft(raw,now)
        assertNotNull(model)
        val all=StopLossOfflineSimulation.suite(model!!)
        assertEquals(4,all.size)
        assertTrue(all.all { it.second.passed && !it.second.brokerOpened && !it.second.orderSubmitted })
        val success=all.first().second
        assertEquals("12,43",success.stopText)
        assertEquals("7",success.quantityText)
        assertTrue(success.trace.any { it.contains("12,43") })
        assertTrue(success.trace.any { it.contains("Anzahl = 7") })
        assertNull(StopLossOfflineSimulation.modelDraft(raw,now+300_001))
        assertNull(StopLossOfflineSimulation.modelDraft(raw.replace("|EUR|","|CHF|"),now))
    }

    @Test fun invalidSyntheticModelDoesNotRunAnyScreenActions() {
        val bad=StopLossPrefillDraft("MISMATCH",0,0,0L)
        val r=StopLossOfflineSimulation.run(StopLossOfflineSimulation.Scenario.HAPPY_PATH,bad)
        assertFalse(r.passed)
        assertFalse(r.brokerOpened)
        assertFalse(r.orderSubmitted)
        assertTrue(r.trace.none { it.contains("Testklick") })
    }

    @Test fun negativeResultsRequireTheExactExpectedGate() {
        val expected=mapOf(
            StopLossOfflineSimulation.Scenario.WRONG_ISIN to
                (StopLossPrefillPolicy.Stage.OPEN_FORM to "PRODUKT_ISIN_NICHT_ERKANNT"),
            StopLossOfflineSimulation.Scenario.BUY_SELECTED to
                (StopLossPrefillPolicy.Stage.VERIFY_FORM to "VERKAUF_NICHT_BESTAETIGT"),
            StopLossOfflineSimulation.Scenario.AMBIGUOUS_STOP_FIELD to
                (StopLossPrefillPolicy.Stage.WRITE_STOP to "STOP_FELD_NICHT_EINDEUTIG")
        )
        assertNull(StopLossOfflineSimulation.expectedBlock(StopLossOfflineSimulation.Scenario.HAPPY_PATH))
        for ((scenario, gate) in expected) {
            val guard=StopLossOfflineSimulation.expectedBlock(scenario)
            assertNotNull(guard)
            assertEquals(gate.first,guard!!.stage)
            assertEquals(gate.second,guard.code)
            val report=StopLossOfflineSimulation.run(scenario)
            assertTrue(report.reason+" / "+report.trace.joinToString("; "),report.passed)
            assertEquals("Sperre wie erwartet: "+gate.second,report.reason)
            assertTrue(report.trace.any { it.contains("Sicherheitssperre in "+gate.first+": "+gate.second) })
            assertEquals("",report.stopText)
            assertEquals("",report.quantityText)
        }
    }

    @Test fun allOfflineScenariosCannotOpenBrokerOrPlaceOrder() {
        val all=StopLossOfflineSimulation.suite()
        assertEquals(4,all.size)
        assertTrue(all.all { it.second.passed && !it.second.brokerOpened && !it.second.orderSubmitted })
    }
}
