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
    @Test fun allOfflineScenariosCannotOpenBrokerOrPlaceOrder() {
        val all=StopLossOfflineSimulation.suite()
        assertEquals(4,all.size)
        assertTrue(all.all { it.second.passed && !it.second.brokerOpened && !it.second.orderSubmitted })
    }
}
