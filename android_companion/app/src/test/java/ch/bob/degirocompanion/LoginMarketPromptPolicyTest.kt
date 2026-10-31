package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LoginMarketPromptPolicyTest {
    @Test fun visibleEmptySearchInputCanExposePromptOnlyAsHint() {
        val prompt = "Mit Namen, ISIN oder Symbol suchen"
        assertTrue(LoginMarketPromptPolicy.isExactPrompt(prompt, null, null,
            editable=true, password=false, sensitive=false))
        assertTrue(LoginMarketPromptPolicy.isExactPrompt(null, prompt, null,
            editable=true, password=false, sensitive=false))
        assertTrue(LoginMarketPromptPolicy.isExactPrompt(null, null, prompt,
            editable=true, password=false, sensitive=false))
        assertFalse(LoginMarketPromptPolicy.isExactPrompt(null, null, null,
            editable=true, password=false, sensitive=false))
        assertFalse(LoginMarketPromptPolicy.isExactPrompt("Gold", null, null,
            editable=true, password=false, sensitive=false))
    }

    @Test fun neverMistakeSensitiveOrNonEditableFieldsForSearchInputs() {
        val prompt = "Mit Namen, ISIN oder Symbol suchen"
        assertFalse(LoginMarketPromptPolicy.isExactPrompt(prompt, null, null,
            editable=true, password=true, sensitive=false))
        assertFalse(LoginMarketPromptPolicy.isExactPrompt(prompt, null, null,
            editable=true, password=false, sensitive=true))
        assertFalse(LoginMarketPromptPolicy.isExactPrompt(prompt, null, null,
            editable=false, password=false, sensitive=false))
        assertFalse(LoginMarketPromptPolicy.usable(true,false,false))
        assertFalse(LoginMarketPromptPolicy.usable(true,true,true))
        assertTrue(LoginMarketPromptPolicy.usable(true,true,false))
    }

    @Test fun exactVisibleMarkersNeverCollectAccountOrCompoundText() {
        val allowed = setOf("Märkte", "News", "Indizes",
            "Mit Namen, ISIN oder Symbol suchen", "Schließen")
        assertEquals("Märkte", LoginMarketPromptPolicy.exactFixedLabel(" Märkte ", allowed))
        assertEquals("Indizes", LoginMarketPromptPolicy.exactFixedLabel("Indizes", allowed))
        assertNull(LoginMarketPromptPolicy.exactFixedLabel("Märkte CHF 504,74",allowed))
        assertNull(LoginMarketPromptPolicy.exactFixedLabel("Kontostand",allowed))
        assertNull(LoginMarketPromptPolicy.exactFixedLabel("Schließen und kaufen",allowed))
    }
}
