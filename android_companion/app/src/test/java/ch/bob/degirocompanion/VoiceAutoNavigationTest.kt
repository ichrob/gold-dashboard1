package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class VoiceAutoNavigationTest {
    @Test fun micTapMayAutomaticallyOpenOneKnownReadOnlyBobPage() {
        for (task in listOf(
            PhoneTask.OPEN_BOB, PhoneTask.OPEN_PRODUCTS, PhoneTask.OPEN_MARKET,
            PhoneTask.OPEN_LONG_REVIEW, PhoneTask.OPEN_LEVERAGE_REVIEW,
            PhoneTask.OPEN_TRADE, PhoneTask.OPEN_SIMULATION, PhoneTask.OPEN_LEARNING,
            PhoneTask.OPEN_RESEARCH, PhoneTask.OPEN_PROBLEMS
        )) {
            assertEquals(task, VoiceAutoNavigation.allowed(PhoneTaskPlan(listOf(task))))
            assertEquals(true, BobNavigation.urlFor(task)!!
                .startsWith("https://bob-private-scanner.onrender.com/?view="))
        }
    }

    @Test fun noAutoExecutionOfSettingsImagePickerOrMultiStep() {
        assertNull(VoiceAutoNavigation.allowed(PhoneTaskPlan(listOf(PhoneTask.OPEN_SETTINGS))))
        assertNull(VoiceAutoNavigation.allowed(PhoneTaskPlan(listOf(PhoneTask.PICK_IMAGES))))
        assertNull(VoiceAutoNavigation.allowed(PhoneTaskPlan(listOf(
            PhoneTask.OPEN_PRODUCTS, PhoneTask.OPEN_LONG_REVIEW))))
        assertNull(VoiceAutoNavigation.allowed(PhoneTaskPlan(listOf(
            PhoneTask.OPEN_PRODUCTS, PhoneTask.OPEN_SETTINGS))))
    }

    @Test fun noAutoExecutionOfUnknownOrUnsafeUtterance() {
        for (phrase in listOf(
            "Goldprodukte und kaufe den besten Hebel",
            "Zeige den Hebel und ändere meinen Stopp",
            "Öffne DEGIRO und melde mich an",
            "Kaufe sofort 300 Euro Gold",
            "Zeige mein Trade Depot und verkaufe"
        )) assertNull(PhoneTaskPlanParser.parse(phrase)?.let(VoiceAutoNavigation::allowed))
    }
}
