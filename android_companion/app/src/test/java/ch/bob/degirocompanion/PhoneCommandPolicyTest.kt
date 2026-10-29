package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class PhoneCommandPolicyTest {
    @Test fun duplicatesExpiredAndCrossSessionNeverExecute() {
        val p=PhoneCommandPolicy();val id="a".repeat(32);val request="b".repeat(32)
        assertFalse(p.accept(id,"c".repeat(32),request,"inspect","",110,100))
        assertFalse(p.accept(id,id,request,"inspect","",100,100))
        assertFalse(p.accept(id,id,request,"inspect","",131,100))
        assertTrue(p.accept(id,id,request,"inspect","",110,100))
        assertFalse(p.accept(id,id,request,"inspect","",110,100))
    }
    @Test fun onlyFixedQueriesAndNoOrders() {
        val id="a".repeat(32)
        for(action in listOf("tap","buy","sell","login","type"))assertFalse(PhoneCommandPolicy().accept(id,id,id,action,"",110,100))
        assertFalse(PhoneCommandPolicy().accept(id,id,id,"search_gold","secret",110,100))
        assertFalse(PhoneCommandPolicy().accept(id,id,id,"search_isin","DE000FE2JJ21",110,100))
        assertTrue(PhoneCommandPolicy().accept(id,id,id,"search_isin","DE000FE2JJ20",110,100))
    }
}
