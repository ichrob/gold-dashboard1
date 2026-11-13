package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class ConnectionErrorPolicyTest {
    @Test fun realErrorBlocksGoldAndPreservesDiagnosticCode() {
        val nodes=listOf(MorningReadPolicy.Node("Connection error"), MorningReadPolicy.Node("Refresh",clickable=true))
        val result=MorningReadPolicy.discoverGold(nodes)
        assertEquals(MorningReadPolicy.Kind.BLOCK,result.kind)
        assertEquals("CONNECTION_ERROR",result.code)
        assertEquals("CONNECTION_ERROR",PhoneDiagnosticPolicy.code(result.code))
        assertTrue(MorningReadUiPolicy.reason(result.code).contains("Verbindungsfehler"))
    }
    @Test fun ordinaryContentIsNotAnErrorAndVariantsAreRecognized() {
        assertFalse(ConnectionErrorPolicy.detected(listOf("Gold", "Refresh")))
        assertFalse(ConnectionErrorPolicy.detected(listOf("News about connection error recovery")))
        for(label in listOf(" Connection ERROR ","Verbindungsfehler","Keine Internetverbindung"))
            assertTrue(ConnectionErrorPolicy.detected(listOf(label)))
    }
    @Test fun failuresNeverExportRawText() {
        assertEquals("SCREEN_LOCKED",WorkflowFailure.code("Gestoppt: Bildschirm gesperrt"))
        assertEquals("ACTION_REJECTED",WorkflowFailure.code("Aktion abgelehnt; kein automatischer Wiederholungsklick"))
        assertEquals("OTHER",WorkflowFailure.code("private arbitrary text"))
    }
}
