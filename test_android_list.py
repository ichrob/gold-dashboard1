import base64,copy,struct,unittest
from datetime import datetime,timezone
import android_list as images
import android_telemetry_http as http
from test_android_telemetry import Handler
NOW=2000000000

def batch():
    def png(suffix):return base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'\0\0\0\rIHDR'+struct.pack('>II',709,1200)+b'\x08\x02\0\0\0'+suffix).decode()
    return {'batchId':'a'*32,'sessionId':'b'*32,'images':[{'at':datetime.fromtimestamp(NOW-10+i,timezone.utc).isoformat(),'png':png(bytes([i])*8)} for i in range(2)]}
class ListTests(unittest.TestCase):
    def test_bounded_original_series(self):
        self.assertEqual(images.validate(batch(),NOW),batch())
        one=batch();one['images']=one['images'][:1]
        self.assertEqual(len(images.validate(one,NOW)['images']),1)
        four=batch()
        for i in (2,3):
            image=dict(four['images'][0]);image['png']=base64.b64encode(base64.b64decode(image['png'])+bytes([i])).decode()
            image['at']=four['images'][-1]['at'];four['images'].append(image)
        self.assertEqual(len(images.validate(four,NOW)['images']),4)
        for mutate in [lambda x:x['images'].clear(),lambda x:x['images'].extend(x['images']*2),lambda x:x['images'][1].update(png=x['images'][0]['png']),lambda x:x['images'][0].update(at='2020-01-01T00:00:00Z'),lambda x:x['images'][0].update(png='bad'),lambda x:x.update(sessionId='bad')]:
            x=batch();mutate(x)
            with self.assertRaises((ValueError,TypeError)):images.validate(x,NOW)
    def test_browser_cannot_upload_and_device_cannot_read(self):
        h=Handler(batch(),auth=True)
        http.route(h,'POST','/api/android-list/upload',lambda *_:self.fail('cookie upload'))
        self.assertEqual(h.code,401)
        h=Handler({},headers={'Authorization':'Bearer '+'a'*64});h.path='/api/android-list/latest?batchId='+'a'*32
        http.route(h,'GET','/api/android-list/latest',lambda *_:self.fail('device read'))
        self.assertEqual(h.code,401)
    def test_requires_matching_live_session_before_insert(self):
        class Result:
            def __init__(self,value):self.value=value
            def fetchone(self):return self.value
        class DB:
            def __init__(self,state):self.state=state;self.inserted=False
            def execute(self,sql,args=()):
                if sql.startswith('SELECT token_hash FROM'):return Result(('device',))
                if sql.startswith('SELECT state'):return Result((self.state,))
                if sql.startswith('SELECT token_hash,payload'):return Result(None)
                if sql.startswith('SELECT count'):return Result((0,))
                if sql.startswith('INSERT'):self.inserted=True
                return Result(None)
        good=dict(sessionId='b'*32,active=True,expiresAt=NOW+60,seenAt=NOW)
        for change in [dict(active=False),dict(expiresAt=NOW),dict(seenAt=NOW-31),dict(sessionId='c'*32)]:
            db=DB({**good,**change})
            with self.assertRaises(PermissionError):images.handle(db,{'action':'list-upload','token':'a'*64,'value':batch()},NOW)
            self.assertFalse(db.inserted)
        db=DB(good)
        self.assertEqual(images.handle(db,{'action':'list-upload','token':'a'*64,'value':batch()},NOW)['batchId'],'a'*32)
        self.assertTrue(db.inserted)
    def test_capture_codes_are_preserved_without_free_text(self):
        from android_observations import CODES
        for code in ('LIST_IMAGES_DELIVERED','LIST_CAPTURE_FAILED','LIST_SCROLL_NO_PROGRESS','KEYBOARD_HIDE_FAILED'):
            self.assertIn(code,CODES)
    def test_separate_routes(self):
        sent=[];h=Handler(batch(),headers={'Authorization':'Bearer '+'a'*64})
        http.route(h,'POST','/api/android-list/upload',lambda p,remote=False:sent.append((p,remote)) or {})
        self.assertEqual(sent[0][0]['action'],'list-upload');self.assertTrue(sent[0][1])
        h=Handler({},auth=True);h.path='/api/android-list/latest?batchId='+'a'*32
        http.route(h,'GET','/api/android-list/latest',lambda p,remote=False:sent.append((p,remote)) or {})
        self.assertEqual(sent[1][0],{'action':'list-get','batchId':'a'*32})
if __name__=='__main__':unittest.main()
