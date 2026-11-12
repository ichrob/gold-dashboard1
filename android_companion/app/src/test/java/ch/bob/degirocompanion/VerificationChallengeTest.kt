package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class VerificationChallengeTest {
    @Test fun visibleChallengesAreBlocked() {
        for (text in listOf("CAPTCHA", "Ich bin kein Roboter", "I'm not a robot",
            "Verify you are human", "Confirm that you are a human",
            "Bestätigen Sie, dass Sie ein Mensch sind", "Sicherheitsüberprüfung",
            "Checking your browser", "Verify\n you are\u00a0human")) {
            assertTrue(text, VerificationChallenge.detected(text))
            assertTrue(LocalWorkflow.protected(WorkflowFrame("nl.degiro.trader", 1,
                listOf(WorkflowNode(text, "", false, true)))))
            val result = ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE,
                listOf(QuoteLayout.Line(text, 0, 0, 500, 30)), "2026-11-12T12:00:00Z")
            assertEquals(text, ProductScreenEvidence.Reason.PROTECTED, result.reason)
            assertTrue(result.draft.isEmpty())
            val step = ProductPageReader().inspect(1,
                listOf(QuoteLayout.Line(text, 0, 0, 500, 30)),
                "2026-11-12T12:00:00Z", false, true, true)
            assertEquals(ProductPageReader.Move.ABORT, step.move)
            assertEquals(ProductPageReader.Cause.UNSAFE_VIEW, step.cause)
            for (node in listOf(MorningReadPolicy.Node(text),
                MorningReadPolicy.Node("", description=text),
                MorningReadPolicy.Node("", hint=text))) {
                val action = MorningReadPolicy.discoverGold(listOf(node))
                assertEquals(MorningReadPolicy.Kind.BLOCK, action.kind)
                assertEquals("PROTECTED_VERIFICATION", action.code)
            }
        }
        assertTrue(PhoneObservationPolicy.mustStop("PROTECTED_VERIFICATION"))
    }
    @Test fun ordinaryProductTextRemainsUsable() {
        for (text in listOf("Gold", "Kursdaten", "Security", "Human Resources", "Brief 10,20")) {
            assertFalse(text, VerificationChallenge.detected(text))
        }
    }
}
