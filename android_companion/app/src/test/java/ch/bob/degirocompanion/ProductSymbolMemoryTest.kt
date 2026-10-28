package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductSymbolMemoryTest {
    private val isin = "DE000FD0S0G4"
    private val other = "DE000FG77MY4"
    private fun line(text: String, x: Int = 0, y: Int = 0) = QuoteLayout.Line(text,x,y,x+250,y+30)
    private fun pair() = listOf(line("Symbol | ISIN"),line("12345678 | $isin",300))
    @Test fun learnsOnlyExplicitUnambiguousSameRowPair() {
        assertEquals(ProductSymbolMemory.Pairing("12345678",isin),ProductSymbolMemory.observe(pair(),false))
        assertNull(ProductSymbolMemory.observe(pair(),true))
        assertNull(ProductSymbolMemory.observe(listOf(line("12345678 | $isin")),false))
        assertNull(ProductSymbolMemory.observe(listOf(line("Symbol | ISIN"),line("12345678 | $isin",300,100)),false))
        assertNull(ProductSymbolMemory.observe(pair()+line(other,0,100),false))
        assertNull(ProductSymbolMemory.observe(pair()+line("Order bestätigen",0,100),false))
        assertNull(ProductSymbolMemory.observe(pair()+line("87654321 | $isin",600),false))
        assertNull(ProductSymbolMemory.observe(listOf(line("Symbol | ISIN 12345678 | DE000FD0S0G5")),false))
        assertNotNull(ProductSymbolMemory.observe(listOf(line("Symbol | ISIN 12345678 | $isin")),false))
    }
    @Test fun conflictingPairNeverSilentlyReplacesPreviousIdentity() {
        assertEquals(isin,ProductSymbolMemory.merge(null,isin))
        assertEquals(isin,ProductSymbolMemory.merge(isin,isin))
        val conflict = ProductSymbolMemory.merge(isin,other)
        assertEquals(ProductSymbolMemory.CONFLICT,conflict)
        assertEquals(conflict,ProductSymbolMemory.merge(conflict,isin))
    }
    @Test fun lookupRequiresIsolatedBrokerHeaderAndSingleKnownSymbol() {
        val header = line("12345678 • Societe Generale OTC | R")
        assertEquals(isin,ProductSymbolMemory.resolve(listOf(header)) { isin })
        assertNull(ProductSymbolMemory.resolve(listOf(line("12345678"))) { isin })
        assertNull(ProductSymbolMemory.resolve(listOf(header)) { null })
        assertNull(ProductSymbolMemory.resolve(listOf(header)) { ProductSymbolMemory.CONFLICT })
        assertNull(ProductSymbolMemory.resolve(listOf(header,line("87654321 • Societe Generale OTC | R"))) { isin })
    }
    @Test fun learnedHintCanStartScrollingButCannotPublishWithoutRealIsin() {
        val reader = ProductPageReader()
        val header = listOf(line("12345678 • Societe Generale OTC | R"))
        assertEquals(ProductPageReader.Move.FORWARD,reader.inspect(1,header,"",false,true,true,identityHint=isin).move)
        val quotes = listOf(line("Geld EUR 10,20"),line("Brief EUR 10,30",0,50))
        assertEquals(ProductPageReader.Move.BACKWARD,reader.inspect(1,quotes,"",false,true,true).move)
        val unverified = reader.inspect(1,header,"",false,false,false,identityHint=isin)
        assertEquals(ProductPageReader.Move.ABORT,unverified.move)
        assertEquals("",unverified.result.draft)
        reader.inspect(1,header,"",false,true,true,identityHint=isin)
        val done = reader.inspect(1,quotes+line(isin,0,100),"",false,true,true)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        reader.inspect(1,header,"",false,true,true,identityHint=isin)
        assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED,reader.inspect(1,listOf(line(other)),"",false,true,true).cause)
        reader.inspect(1,header,"",false,true,true,identityHint=isin)
        assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED,reader.inspect(1,header,"",false,true,true,identityHint=other).cause)
    }
}
