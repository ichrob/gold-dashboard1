package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChatShareHandoffTest {
    @Test fun userSharedSingleReadOnlyCommandsAreRecognized() {
        assertEquals(PhoneTask.OPEN_PRODUCTS,
            ChatShareHandoff.parse(ChatShareHandoff.PRODUCTS))
        assertEquals(PhoneTask.OPEN_PRODUCTS,
            ChatShareHandoff.parse("Zeige meine Goldprodukte"))
        assertEquals(PhoneTask.OPEN_MARKET,
            ChatShareHandoff.parse("BOB-HANDY/1|OPEN_MARKET"))
        assertEquals(PhoneTask.OPEN_TRADE,
            ChatShareHandoff.parse("BOB-HANDY/1|OPEN_TRADE"))
    }

    @Test fun exactAppLinksSharedAsPlainTextNeedFreshConsent() {
        val links = listOf(
            "https://bob-private-scanner.onrender.com/handy/OPEN_PRODUCTS",
            "bobhandy://handoff/OPEN_PRODUCTS"
        )
        for (link in links) {
            val task = ChatShareHandoff.parse(link)
            assertEquals(PhoneTask.OPEN_PRODUCTS, task)
            val gate = PhoneTaskApproval()
            assertFalse("An incoming link must not execute by itself", gate.consume(task, 100L))
            gate.approve(task!!, 101L)
            assertTrue(gate.consume(task, 102L))
            assertFalse(gate.consume(task, 103L))
        }
    }

    @Test fun sharedUrlsWithExtraDataOrArbitraryDomainsStayBlocked() {
        for (raw in listOf(
            "https://bob-private-scanner.onrender.com/handy/OPEN_PRODUCTS?buy=1",
            "https://bob-private-scanner.onrender.com/handy/OPEN_PRODUCTS#x",
            "https://bob-private-scanner.onrender.com/handy/OPEN_PRODUCTS/",
            "https://bob-private-scanner.onrender.com/handy/OPEN_PRODUCTS\nextra",
            "https://bob-private-scanner.onrender.com/handy/PLACE_ORDER",
            "https://bob-private-scanner.onrender.com.evil.example/handy/OPEN_PRODUCTS",
            "https://example.org/handy/OPEN_PRODUCTS",
            "https://bob-private-scanner.onrender.com/handy/OPEN_PRODUCTS and buy",
            "bobhandy://handoff/OPEN_PRODUCTS?extra=1",
            "bobhandy://handoff/OPEN_PRODUCTS;BUY"
        )) assertNull(raw, ChatShareHandoff.parse(raw))
    }

    @Test fun untrustedBrokerActionsArbitraryUrlsAndChainsAreRejected() {
        listOf(
            "BOB-HANDY/1|PLACE_ORDER",
            "BOB-HANDY/1|OPEN_SETTINGS", "BOB-HANDY/1|PICK_IMAGES",
            "BOB-HANDY/1|OPEN_PRODUCTS|OPEN_TRADE",
            "BOB-HANDY/1|OPEN_PRODUCTS\nBOB-HANDY/1|OPEN_TRADE",
            "Zeige meine Goldprodukte und danach Simulationen",
            "Zeige meine Goldprodukte und kaufe Gold",
            "Kaufe Gold", "Logge dich bei DEGIRO ein",
            "https://bob-private-scanner.onrender.com/",
            "javascript:alert(1)", "BOB-FERN/1|abc",
            "BOB-HANDY/1|OPEN_PRODUCTS;DELETE",
            "BOB-HANDY/1|OPEN_PRODUCTS\u0000",
            "BOB-HANDY/1|OPEN_PRODUCTS" + "x".repeat(200),
            "Bob Goldprodukte\nKontodaten: privat",
            "BOB-AUFTRAG: PRODUKTBILDER_WAEHLEN",
            "BOB-AUFTRAG: ANDROID_EINSTELLUNGEN_OEFFNEN"
        ).forEach { assertNull(it, ChatShareHandoff.parse(it)) }
    }

    @Test fun localApprovalRemainsOneShotAndRevocable() {
        val gate = PhoneTaskApproval()
        val task = ChatShareHandoff.parse(ChatShareHandoff.PRODUCTS)
        assertEquals(PhoneTask.OPEN_PRODUCTS, task)
        assertFalse(gate.consume(task, 100))
        gate.approve(task!!, 101)
        assertTrue(gate.consume(task, 102))
        assertFalse(gate.consume(task, 103))
        gate.approve(task, 200)
        gate.clear() // screen switch / STOPP
        assertFalse(gate.consume(task, 201))
    }
}
