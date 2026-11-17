package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class FinalReadReturnPolicyTest {
    private val isin = "DE000FB0CVK2"
    private val draft = "BOB APP-LESEENTWURF – NICHT VERIFIZIERT\nISIN: $isin\nGeld (Anzeige ungeprüft): 6,74"
    private fun allowed(
        code: String = "READ",
        evidence: String = draft,
        expected: String = isin,
        previous: Int? = 12,
        current: Int? = 12,
        pkg: String? = ProductScreenEvidence.PACKAGE,
        awake: Boolean = true,
        locked: Boolean = false,
        session: Boolean = true
    ) = FinalReadReturnPolicy.allowed(code, evidence, expected, previous,
        current, pkg, awake, locked, session)

    @Test fun abortedReadReturnsOnlyWithAnExplicitSafeLocalStatusScope() {
        assertTrue(FinalReadReturnPolicy.allowedAbort("RETURN_NOT_CONFIRMED",
            ProductScreenEvidence.PACKAGE,true,false,true,true))
        for(code in listOf("COMPLETE","USER_INTERRUPTED","SCREEN_LOCKED",
            "PROTECTED_VIEW","RETURN_FAILED")) {
            assertFalse(FinalReadReturnPolicy.allowedAbort(code,
                ProductScreenEvidence.PACKAGE,true,false,true,true))
        }
        assertFalse(FinalReadReturnPolicy.allowedAbort("RETURN_NOT_CONFIRMED",
            ProductScreenEvidence.PACKAGE,true,false,true,false))
        assertFalse(FinalReadReturnPolicy.allowedAbort("RETURN_NOT_CONFIRMED",
            "com.android.systemui",true,false,true,true))
        assertFalse(FinalReadReturnPolicy.allowedAbort("RETURN_NOT_CONFIRMED",
            ProductScreenEvidence.PACKAGE,false,false,true,true))
        assertFalse(FinalReadReturnPolicy.allowedAbort("RETURN_NOT_CONFIRMED",
            ProductScreenEvidence.PACKAGE,true,true,true,true))
        assertFalse(FinalReadReturnPolicy.allowedAbort("RETURN_NOT_CONFIRMED",
            ProductScreenEvidence.PACKAGE,true,false,false,true))
    }

    @Test fun successfulLastProductCanReturnToLocalStatusWithoutBrokerBack() {
        assertTrue(allowed())
    }

    private val lastDetail = listOf(
        MorningReadPolicy.Node(isin),
        MorningReadPolicy.Node("Übersicht"),
        MorningReadPolicy.Node("Kursdaten"),
        MorningReadPolicy.Node("Geld EUR 6,74")
    )
    private fun safeBack(
        code: String = "READ",
        evidence: String = draft,
        expected: String = isin,
        previous: Int? = 12,
        current: Int? = 12,
        pkg: String? = ProductScreenEvidence.PACKAGE,
        awake: Boolean = true,
        locked: Boolean = false,
        session: Boolean = true,
        nodes: List<MorningReadPolicy.Node> = lastDetail
    ): Boolean = FinalReadReturnPolicy.safeLastProductBack(
        code,evidence,expected,previous,current,pkg,awake,locked,session,nodes)

    @Test fun verifiedLastProductMaySendOneNativeBack() {
        assertTrue(safeBack())
    }

    @Test fun finalBackFailsClosedForOrderLoginDifferentIdentityAndInputs() {
        assertFalse(safeBack(nodes=lastDetail+MorningReadPolicy.Node("Order bestätigen")))
        assertFalse(safeBack(nodes=lastDetail+MorningReadPolicy.Node("Limitpreis")))
        assertFalse(safeBack(nodes=lastDetail+MorningReadPolicy.Node("Passwort")))
        assertFalse(safeBack(nodes=lastDetail+MorningReadPolicy.Node("",editable=true)))
        assertFalse(safeBack(nodes=lastDetail+MorningReadPolicy.Node("",sensitive=true)))
        assertFalse(safeBack(nodes=lastDetail+MorningReadPolicy.Node("DE000FE2JJ20")))
        assertFalse(safeBack(nodes=listOf(MorningReadPolicy.Node("Märkte"))))
        assertFalse(safeBack(nodes=emptyList()))
    }

    @Test fun finalBackRequiresSameAnchoredWindowExplicitSessionAndRealRead() {
        assertFalse(safeBack(code="NO_QUOTES"))
        assertFalse(safeBack(code="COMPLETE"))
        assertFalse(safeBack(evidence=""))
        assertFalse(safeBack(expected="DE000FE2JJ20"))
        assertFalse(safeBack(previous=null))
        assertFalse(safeBack(current=13))
        assertFalse(safeBack(pkg="com.android.systemui"))
        assertFalse(safeBack(session=false))
        assertFalse(safeBack(awake=false))
        assertFalse(safeBack(locked=true))
    }

    @Test fun noReturnForUnverifiedOrAbortedProduct() {
        for (code in listOf("NO_QUOTES", "RETURN_FAILED", "SEEK_LIMIT",
                "PROTECTED_VIEW", "USER_INTERRUPTED", "COMPLETE"))
            assertFalse(allowed(code = code))
        assertFalse(allowed(evidence = ""))
        assertFalse(allowed(evidence = draft.replace(isin, "DE000SX7PE82")))
        assertFalse(allowed(expected = "WRONG"))
        assertFalse(allowed(session = false))
    }

    @Test fun noReturnFromOtherAppChangedWindowOrLockedDevice() {
        assertFalse(allowed(previous = null))
        assertFalse(allowed(current = 13))
        assertFalse(allowed(pkg = "com.android.systemui"))
        assertFalse(allowed(pkg = null))
        assertFalse(allowed(awake = false))
        assertFalse(allowed(locked = true))
    }
}
