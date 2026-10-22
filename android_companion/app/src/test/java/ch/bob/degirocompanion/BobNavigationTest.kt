package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BobNavigationTest {
    @Test fun websiteActionsAlwaysRemainOnBobsOwnOrigin() {
        val sections = listOf(
            PhoneTask.OPEN_BOB, PhoneTask.OPEN_MARKET, PhoneTask.OPEN_PRODUCTS,
            PhoneTask.OPEN_LEVERAGE_REVIEW,
            PhoneTask.OPEN_LONG_REVIEW,
            PhoneTask.OPEN_TRADE, PhoneTask.OPEN_SIMULATION,
            PhoneTask.OPEN_LEARNING, PhoneTask.OPEN_RESEARCH)
        for (task in sections) {
            assertTrue(BobNavigation.urlFor(task)!!.startsWith(BobNavigation.origin + "?view="))
        }
        assertEquals("https://bob-private-scanner.onrender.com/?view=products#products",
            BobNavigation.urlFor(PhoneTask.OPEN_PRODUCTS))
        assertEquals("https://bob-private-scanner.onrender.com/?view=products-long#products-long",
            BobNavigation.urlFor(PhoneTask.OPEN_LONG_REVIEW))
        assertEquals("https://bob-private-scanner.onrender.com/?view=products-leverage#products-leverage",
            BobNavigation.urlFor(PhoneTask.OPEN_LEVERAGE_REVIEW))
        assertEquals("https://bob-private-scanner.onrender.com/?view=overview#overview",
            BobNavigation.urlFor(PhoneTask.OPEN_MARKET))
    }

    @Test fun rejectsExternalDestinationsAndNonBrowserActions() {
        assertNull(BobNavigation.urlFor(PhoneTask.PICK_IMAGES))
        assertNull(BobNavigation.urlFor(PhoneTask.OPEN_SETTINGS))
        for (value in listOf("https://evil.example/", "//evil", "degiro",
                "../login", "products?buy=true", "products#orders",
                "trade/submit", "http://bob-private-scanner.onrender.com/")) {
            assertNull(BobNavigation.urlForSection(value))
        }
    }
}
