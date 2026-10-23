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

    @Test fun repeatedPhoneOpenCreatesFreshBrowserNavigationForGoldStart() {
        val first = BobNavigation.urlForSection("products", 1001L)
        val second = BobNavigation.urlForSection("products", 1002L)
        assertEquals("https://bob-private-scanner.onrender.com/?view=products&bobvisit=1001#products", first)
        assertEquals("https://bob-private-scanner.onrender.com/?view=products&bobvisit=1002#products", second)
        assertTrue(first != second)
        assertEquals("https://bob-private-scanner.onrender.com/?view=products-long&bobvisit=8#products-long",
            BobNavigation.urlForSection("products-long", 8L))
        assertEquals("https://bob-private-scanner.onrender.com/?view=products#products",
            BobNavigation.urlForSection("products", -1L))
        assertNull(BobNavigation.urlForSection("https://example.invalid", 1003L))
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
