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
    def test_bounded_original_pair(self):
        self.assertEqual(images.validate(batch(),NOW),batch())
        for mutate in [lambda x:x['images'].pop(),lambda x:x['images'].append(x['images'][0]),lambda x:x['images'][1].update(png=x['images'][0]['png']),lambda x:x['images'][0].update(at='2020-01-01T00:00:00Z'),lambda x:x['images'][0].update(png='bad'),lambda x:x.update(sessionId='bad')]:
            x=batch();mutate(x)
            with self.assertRaises((ValueError,TypeError)):images.validate(x,NOW)
    def test_browser_cannot_upload_and_device_cannot_read(self):
        h=Handler(batch(),auth=True)
        http.route(h,'POST','/api/android-list/upload',lambda *_:self.fail('cookie upload'))
        self.assertEqual(h.code,401)
        h=Handler({},headers={'Authorization':'Bearer '+'a'*64});h.path='/api/android-list/latest?batchId='+'a'*32
        http.route(h,'GET','/api/android-list/latest',lambda *_:self.fail('device read'))
        self.assertEqual(h.code,401)
    def test_separate_routes(self):
        sent=[];h=Handler(batch(),headers={'Authorization':'Bearer '+'a'*64})
        http.route(h,'POST','/api/android-list/upload',lambda p,remote=False:sent.append((p,remote)) or {})
        self.assertEqual(sent[0][0]['action'],'list-upload');self.assertTrue(sent[0][1])
        h=Handler({},auth=True);h.path='/api/android-list/latest?batchId='+'a'*32
        http.route(h,'GET','/api/android-list/latest',lambda p,remote=False:sent.append((p,remote)) or {})
        self.assertEqual(sent[1][0],{'action':'list-get','batchId':'a'*32})
if __name__=='__main__':unittest.main()
