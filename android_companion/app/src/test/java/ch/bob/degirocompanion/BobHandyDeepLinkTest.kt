package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class BobHandyDeepLinkTest {
    @Test fun exactHarmlessLinksRoundTrip() {
        for (task in listOf(PhoneTask.OPEN_BOB, PhoneTask.OPEN_PRODUCTS,
                PhoneTask.OPEN_TRADE, PhoneTask.OPEN_SIMULATION,
                PhoneTask.OPEN_MARKET, PhoneTask.OPEN_LEARNING, PhoneTask.OPEN_RESEARCH,
                PhoneTask.OPEN_LEVERAGE_REVIEW, PhoneTask.OPEN_LONG_REVIEW)) {
            val link = BobHandyDeepLink.linkFor(task)
            assertNotNull(task.name, link)
            assertEquals(task, BobHandyDeepLink.parse(link))
        }
    }

    @Test fun unknownOrBrokerDangerousLinksFailClosed() {
        listOf(null, "", "bobhandy://handoff/",
            "bobhandy://handoff/OPEN_SETTINGS",
            "bobhandy://handoff/PICK_IMAGES",
            "bobhandy://handoff/DEGIRO_LOGIN",
            "bobhandy://handoff/PLACE_ORDER",
            "bobhandy://handoff/OPEN_PRODUCTS?trade=true",
            "bobhandy://handoff/OPEN_PRODUCTS#trade",
            "bobhandy://handoff/OPEN_PRODUCTS/OPEN_TRADE",
            "bobhandy://handoff/%4fPEN_PRODUCTS",
            "bobhandy://handoff/OPEN_PRODUCTS%0A",
            "bobhandy://badhost/OPEN_PRODUCTS",
            "bobhandy://user@handoff/OPEN_PRODUCTS",
            "bobhandy://handoff:444/OPEN_PRODUCTS",
            "BOBHANDY://handoff/OPEN_PRODUCTS",
            "https://bob-private-scanner.onrender.com/#products",
            "bobhandy://handoff/OPEN_PRODUCTS;BUY",
            "bobhandy://handoff/OPEN_PRODUCTS\nBUY",
            "bobhandy://handoff/" + "A".repeat(200)
        ).forEach { assertNull(it, BobHandyDeepLink.parse(it)) }
    }

    @Test fun importingALinkDoesNotGrantApproval() {
        val task = BobHandyDeepLink.parse("bobhandy://handoff/OPEN_PRODUCTS")
        val gate = PhoneTaskApproval()
        assertFalse(gate.consume(task, 1000))
        gate.approve(task!!, 1200)
        gate.clear()
        assertFalse(gate.consume(task, 1201))
    }
}
