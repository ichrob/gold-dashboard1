package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class EntryReadRequestTest {
    @Test fun requiresBoundedOriginalListAndValidIdentity() {
        val now=Instant.parse("2026-11-16T13:00:00Z").toEpochMilli()
        val id="a".repeat(32);val batch="b".repeat(32);val isin="DE000FD0S0G4"
        assertTrue(EntryReadRequest.valid(id,isin,batch,"2026-11-16T12:00:00Z",now))
        assertFalse(EntryReadRequest.valid(id,isin,batch,"2026-11-15T12:00:00Z",now))
        assertFalse(EntryReadRequest.valid(id,isin,batch,"2026-11-16T13:00:01Z",now))
        assertFalse(EntryReadRequest.valid(id,isin,batch,"2026-11-16T12:00:00",now))
        assertFalse(EntryReadRequest.valid("bad",isin,batch,"2026-11-16T12:00:00Z",now))
        assertFalse(EntryReadRequest.valid(id,"bad",batch,"2026-11-16T12:00:00Z",now))
    }
    @Test fun commandCannotReplayOrOutliveItsSession() {
        val p=PhoneCommandPolicy();val session="a".repeat(32);val id="b".repeat(32)
        assertTrue(p.accept(session,session,id,"entry_read","DE000FD0S0G4",1010,1000))
        assertFalse(p.accept(session,session,id,"entry_read","DE000FD0S0G4",1010,1000))
        assertFalse(PhoneCommandPolicy().accept(session,"c".repeat(32),id,"entry_read","DE000FD0S0G4",1010,1000))
        assertFalse(PhoneCommandPolicy().accept(session,session,id,"entry_read","DE000FD0S0G4",999,1000))
    }
}
