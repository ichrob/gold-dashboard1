package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class SearchResourceIdentityTest {
    @Test fun recognizesSearchResourceNamingStylesWithoutVisiblePlaceholder() {
        for(id in listOf("search-input","product-search-input","searchInput","productSearchInput",
            "searchinput","productsearchinput","nl.degiro.trader:id/search_input","search_src_text")) {
            val input=MorningReadPolicy.Node("",id=id,editable=true,focused=false)
            val launcher=MorningReadPolicy.Node("Order platzieren",clickable=true)
            assertEquals(id,MorningReadPolicy.Kind.FOCUS,MorningReadPolicy.discoverGold(listOf(input,launcher)).kind)
            assertEquals(id,MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(input.copy(focused=true),launcher)).kind)
            assertEquals(id,MorningReadPolicy.Kind.SUBMIT,MorningReadPolicy.discoverGold(listOf(input.copy(focused=true,text="Gold",imeEnter=true),launcher)).kind)
            assertEquals(id,MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(input,launcher,MorningReadPolicy.Node("Limitpreis"))).kind)
        }
    }
    @Test fun doesNotInferSearchFromUnrelatedSubstringOrPackage() {
        for(id in listOf("research","researchInput","searchlight","amount","com.search:id/amount","order_quantity"))
            assertFalse(id,MorningReadPolicy.isSearchInput(id,"",""))
    }
}
