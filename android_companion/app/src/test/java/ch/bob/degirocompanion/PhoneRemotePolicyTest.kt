package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class PhoneRemotePolicyTest {
    @Test fun requiresActiveSessionAndForegroundUnlockedIdlePhone() {
        for(action in listOf("READ_PAGE","SEARCH_GOLD")) {
            assertNull(PhoneRemotePolicy.reject(action,true,false,true,true,false))
            assertEquals("EXPIRED",PhoneRemotePolicy.reject(action,false,false,true,true,false))
            assertEquals("EXPIRED",PhoneRemotePolicy.reject(action,true,true,true,true,false))
            assertEquals("LOCKED",PhoneRemotePolicy.reject(action,true,false,false,true,false))
            assertEquals("WRONG_APP",PhoneRemotePolicy.reject(action,true,false,true,false,false))
            assertEquals("BUSY",PhoneRemotePolicy.reject(action,true,false,true,true,true))
        }
    }
    @Test fun stopIsAllowedWhileBusyButUnknownActionsNeverExecute() {
        assertNull(PhoneRemotePolicy.reject("STOP",true,false,false,false,true))
        for(action in listOf("CLICK","BUY","SELL","LOGIN","SET_TEXT","OPEN_URL",""))
            assertEquals("REJECTED",PhoneRemotePolicy.reject(action,true,false,true,true,false))
    }
}
