"""Offline exact reconstruction; no production DB writes or live image migration."""
import base64
import copy
import json
import struct
import unittest
from datetime import datetime, timezone

import android_image_reference_codec as codec
import android_list

OWNER_A='a'*64
OWNER_B='b'*64
NOW=datetime(2026,11,1,13,30,tzinfo=timezone.utc).timestamp()


def png(marker):
    raw=(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'+
         struct.pack('>II',256,512)+b'\x08\x02\x00\x00\x00'+marker)
    assert len(raw)>=33
    return base64.b64encode(raw).decode()


def batch(batch_id,images):
    stamp=datetime.fromtimestamp(NOW-10,timezone.utc).isoformat()
    return {'batchId':batch_id*32,'sessionId':'f'*32,
            'images':[{'at':stamp,'png':v,
                       'appText':{'before':['private app text'],
                                  'after':['private app text']}}
                      for v in images]}


class PureLosslessReferenceCodecTests(unittest.TestCase):
    def test_two_batches_share_one_private_object_with_exact_restore(self):
        a=png(b'original A 1')
        b=png(b'original B 2')
        first=batch('1',[a,b])
        second=batch('2',[a])
        originals=[copy.deepcopy(first),copy.deepcopy(second)]
        android_list.validate(first,NOW)
        android_list.validate(second,NOW)

        p1,o1=codec.pack_batch(first,OWNER_A)
        p2,o2=codec.pack_batch(second,OWNER_A)
        self.assertEqual(first,originals[0])
        self.assertEqual(second,originals[1])
        self.assertNotIn('png',p1['images'][0])
        self.assertEqual(set(o1)&set(o2),set(o2))
        self.assertEqual(len({**o1,**o2}),2)
        self.assertEqual(codec.restore_batch(p1,{**o1,**o2},OWNER_A),first)
        self.assertEqual(codec.restore_batch(p2,{**o1,**o2},OWNER_A),second)
        self.assertEqual(android_list.validate(codec.restore_batch(p1,o1,OWNER_A),NOW),first)
        self.assertEqual(android_list.validate(codec.restore_batch(p2,o2,OWNER_A),NOW),second)
        self.assertEqual(p1['images'][0]['at'],first['images'][0]['at'])
        self.assertEqual(p1['images'][0]['appText'],first['images'][0]['appText'])

    def test_different_device_scopes_cannot_cross_read(self):
        original=batch('1',[png(b'private same')])
        pa,oa=codec.pack_batch(original,OWNER_A)
        pb,ob=codec.pack_batch(original,OWNER_B)
        self.assertNotEqual(next(iter(oa)),next(iter(ob)))
        self.assertEqual(codec.restore_batch(pa,oa,OWNER_A),original)
        self.assertEqual(codec.restore_batch(pb,ob,OWNER_B),original)
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            codec.restore_batch(pa,oa,OWNER_B)

    def test_missing_tampered_and_ambiguous_pointers_fail_closed(self):
        original=batch('1',[png(b'pristine 0')])
        p,obj=codec.pack_batch(original,OWNER_A)
        with self.assertRaisesRegex(ValueError,'missing'):
            codec.restore_batch(p,{},OWNER_A)
        tampered={next(iter(obj)):png(b'altered 1')}
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            codec.restore_batch(p,tampered,OWNER_A)
        ambiguous=copy.deepcopy(p)
        ambiguous['images'][0]['png']=original['images'][0]['png']
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            codec.restore_batch(ambiguous,obj,OWNER_A)
        missing=copy.deepcopy(p)
        missing['images'][0][codec._REF]='x'*64
        with self.assertRaisesRegex(ValueError,'Invalid image reference'):
            codec.restore_batch(missing,obj,OWNER_A)
        self.assertNotIn(codec._REF,json.dumps(original))

    def test_duplicate_in_same_batch_never_bypasses_existing_rejection(self):
        same=png(b'repeated 0')
        with self.assertRaises(ValueError):
            codec.pack_batch(batch('1',[same,same]),OWNER_A)

    def test_invalid_base64_png_shape_or_scope_never_mutates(self):
        original=batch('1',[png(b'pristine 0')])
        before=copy.deepcopy(original)
        with self.assertRaises(ValueError):
            codec.pack_batch(original,'bad-scope')
        broken=copy.deepcopy(original)
        broken['images'][0]['png']='random-not-base64'
        with self.assertRaises(ValueError):
            codec.pack_batch(broken,OWNER_A)
        invalid=copy.deepcopy(original)
        invalid['images'][0]['appText']['after']=['different']
        # The standalone codec intentionally preserves the original nested
        # metadata verbatim; the existing validator still rejects its
        # semantic inconsistencies before admission to production.
        p,o=codec.pack_batch(invalid,OWNER_A)
        with self.assertRaises(ValueError):
            android_list.validate(codec.restore_batch(p,o,OWNER_A),NOW)
        self.assertEqual(original,before)

    def test_scope_and_reconstruction_refuse_unknown_private_fields(self):
        original=batch('1',[png(b'pristine 0')])
        original['images'][0]['privateKey']='should-not-be-accepted'
        with self.assertRaisesRegex(ValueError,'Invalid image shape'):
            codec.pack_batch(original,OWNER_A)
        for bad in (None,1,True,'z'*64,'a'*63,'A'*64):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    codec.pack_batch(batch('1',[png(b'valid 000')]),bad)


if __name__=='__main__':
    unittest.main()
