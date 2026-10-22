package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PhoneTaskProtocolTest {
    @Test fun onlyThreeExplicitLocalTasksAccepted() {
        assertEquals(PhoneTask.OPEN_BOB, PhoneTaskProtocol.parse(PhoneTaskProtocol.OPEN_BOB))
        assertEquals(PhoneTask.PICK_IMAGES, PhoneTaskProtocol.parse(PhoneTaskProtocol.PICK_IMAGES))
        assertEquals(PhoneTask.OPEN_SETTINGS, PhoneTaskProtocol.parse(PhoneTaskProtocol.OPEN_SETTINGS))
    }

    @Test fun rejectsUntrustedOrTradingCommands() {
        listOf(
            "BOB-AUFTRAG: DEGIRO_LOGIN",
            "BOB-AUFTRAG: ORDER_KAUFEN",
            "BOB-AUFTRAG: BOB_OEFFNEN\nBOB-AUFTRAG: ORDER_KAUFEN",
            "BOB-AUFTRAG: BOB_OEFFNEN; rm -rf /",
            "Bitte auf Kauf klicken",
            "BOB-AUFTRAG: BOB_OEFFNEN\u0000",
            "BOB-AUFTRAG: BOB_OEFFNEN " + "A".repeat(200)
        ).forEach { assertNull(PhoneTaskProtocol.parse(it)) }
    }

    @Test fun whitespaceAroundSingleCommandIsFine() {
        assertEquals(PhoneTask.OPEN_BOB, PhoneTaskProtocol.parse("\n " + PhoneTaskProtocol.OPEN_BOB + " \n"))
    }
}
