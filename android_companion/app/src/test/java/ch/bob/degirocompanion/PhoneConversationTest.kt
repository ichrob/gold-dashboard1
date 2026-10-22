package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PhoneConversationTest {
    @Test fun repeatOnlyPreviouslyLaunchedHarmlessTaskAndRequireFreshApproval() {
        val session = PhoneConversation()
        assertNull(session.interpret("Nochmal", 100))
        session.recordLaunched(PhoneTask.OPEN_PRODUCTS, 200)
        assertEquals(listOf(PhoneTask.OPEN_PRODUCTS), session.interpret("Und jetzt die Goldprodukte", 300)?.steps)
        assertEquals(listOf(PhoneTask.OPEN_PRODUCTS), session.interpret("Mach das nochmal!", 1000)?.steps)
        assertNull(session.interpret("nochmal", 120200))
        assertNull(session.interpret("nochmal und kaufe Gold", 1000))
        session.clear()
        assertNull(session.interpret("nochmal", 2000))
    }

    @Test fun followUpsAreReadOnlyAndBlockedWhenMixedWithTrading() {
        val session = PhoneConversation()
        session.recordLaunched(PhoneTask.OPEN_MARKET, 1000)
        assertEquals(listOf(PhoneTask.OPEN_SIMULATION), session.interpret("Und jetzt die Simulationen", 2000)?.steps)
        assertNull(session.interpret("und danach kaufe Gold", 2000))
        assertNull(session.interpret("wie ist mein Depot", 2000))
        assertEquals(listOf(PhoneTask.OPEN_PRODUCTS, PhoneTask.OPEN_LEARNING),
            session.interpret("Zeige meine Goldprodukte und danach zeige meine Lernergebnisse", 2000)?.steps)
    }
    @Test fun disallowRepeatingSensitiveLocalPickerOrSettings() {
        val session = PhoneConversation()
        session.recordLaunched(PhoneTask.OPEN_PRODUCTS, 100)
        session.recordLaunched(PhoneTask.PICK_IMAGES, 200)
        assertNull(session.interpret("nochmal", 250))
        session.recordLaunched(PhoneTask.OPEN_SETTINGS, 300)
        assertNull(session.interpret("nochmal", 350))
        session.recordLaunched(PhoneTask.OPEN_PRODUCTS, 400)
        assertEquals(listOf(PhoneTask.OPEN_PRODUCTS), session.interpret("nochmal", 450)?.steps)
    }

    @Test fun whyRefersOnlyToRecentSuccessfulProductExplanation() {
        val session=PhoneConversation()
        assertNull(session.interpret("Warum?", 100))
        session.recordLaunched(PhoneTask.OPEN_PRODUCTS, 200)
        assertNull(session.interpret("Warum?", 300))
        session.recordLaunched(PhoneTask.OPEN_LONG_REVIEW, 400)
        assertEquals(listOf(PhoneTask.OPEN_LONG_REVIEW),
            session.interpret("Und warum?", 500)?.steps)
        session.recordLaunched(PhoneTask.OPEN_LEVERAGE_REVIEW, 600)
        assertEquals(listOf(PhoneTask.OPEN_LEVERAGE_REVIEW),
            session.interpret("Wieso?", 700)?.steps)
        assertNull(session.interpret("Warum?", 120601))
        assertNull(session.interpret("Warum und kaufe jetzt", 800))
        session.clear()
        assertNull(session.interpret("Warum?", 850))
    }
}
