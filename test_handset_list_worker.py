import json
import subprocess
import unittest
from unittest.mock import patch
import handset_list_worker as worker

class WorkerTests(unittest.TestCase):
    def test_working_bitmaps_close_between_passes_and_on_native_failure(self):
        from PIL import Image
        for fail in (False,True):
            source=Image.new('RGB',(300,600),'white')
            working=[]
            original_resize=Image.Image.resize
            def resize(image,*args,**kwargs):
                value=original_resize(image,*args,**kwargs)
                working.append(value)
                return value
            def engine(*args,**kwargs):
                if fail:raise RuntimeError('native engine failure')
                # The preceding pass is already closed before the next pass.
                for previous in working[:-1]:
                    with self.assertRaises(ValueError):previous.getpixel((0,0))
                return [],None
            with patch.object(Image.Image,'resize',resize),patch('memory_watch.release_free_pages'):
                if fail:
                    with self.assertRaises(RuntimeError):worker.recognize_image(source,engine)
                else:self.assertEqual(worker.recognize_image(source,engine),['','',''])
            for image in working:
                with self.assertRaises(ValueError):image.getpixel((0,0))
            self.assertEqual(source.getpixel((0,0)),(255,255,255))
            source.close()

    def test_memory_deferrals_are_bounded_across_saved_receipts(self):
        receipt=None
        for count in range(1,25):
            receipt=worker.deferred_memory_receipt('a'*32,receipt)
            self.assertEqual(receipt['memoryDeferrals'],count)
            self.assertEqual(receipt['retryAllowed'],count<24)
            self.assertEqual(receipt['stage'],'waiting-memory' if count<24 else 'read-failed')
        self.assertEqual(receipt['error'],'MemoryError')
        self.assertEqual(receipt['reason'],'OCR_MEMORY_WAIT_EXHAUSTED')
        for invalid in (-1,True,'3',None):
            self.assertEqual(worker.memory_deferrals({'memoryDeferrals':invalid}),0)
        pending=worker.deferred_memory_receipt('a'*32,{'memoryDeferrals':4},enhanced=True)
        self.assertTrue(pending['enhancedPending'])
        later=worker.deferred_memory_receipt('a'*32,pending)
        self.assertTrue(later['enhancedPending'])
        self.assertEqual(later['memoryDeferrals'],6)

    def test_rejected_list_has_only_anonymous_bounded_counts(self):
        raw={'version':1,'uniqueRows':4,'expectedRows':10,
             'imagesTotal':3,'imagesWithRows':2,'conflictingRows':0,
             'duplicateRows':1,'reason':'incomplete'}
        self.assertEqual(worker.bounded_list_diagnostics(raw),raw)
        for changed in (
            {'isin':'DE000TEST000'}, {'rawText':'account secret'},
            {'uniqueRows':11}, {'uniqueRows':True}, {'imagesTotal':0},
            {'reason':'unknown'}):
            value={**raw,**changed}
            self.assertIsNone(worker.bounded_list_diagnostics(value))
        failure=worker.ListVerificationError('Do not log raw OCR',raw)
        self.assertEqual(failure.diagnostics,raw)
        self.assertNotIn('DE000',json.dumps(failure.diagnostics))

    def test_same_screenshot_complement_keeps_only_twice_verified_rows(self):
        script=r"""
const {complementImage,parse}=require('./handset_list_parse');
const fs=require('fs'),vm=require('vm'),context={window:{}};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),context);
const valid=context.window.BobDegiro.validIsin;
function id(n) {
 const prefix='DE000ZZ'+String(n).padStart(4,'0');
 for(let i=0;i<10;i++)if(valid(prefix+i))return prefix+i;
 throw Error('No valid id');
}
function row(n,bp=4000) {
 return 'SG Gold Turbo BEST Open-End Call BAR 4000 BP '+bp+' Bv 10 | '+
   id(n)+' Societe Generale OTC EUR';
}
const phone=[Array.from({length:8},(_,i)=>row(i+1)).join('\n')];
phone.push(phone[0]);
const native=[Array.from({length:4},(_,i)=>row(i+7)).join('\n')];
native.push(native[0],native[0]);
const merged=complementImage(phone,native);
if(!merged||merged.length!==2)throw Error('No safe complement');
const result=parse([merged],'2026-11-18T18:43:10Z');
if(result.items.length!==10 || new Set(result.items.map(x=>x.isin)).size!==10)
 throw Error('Not ten proven identities');
if(complementImage(phone,native.map(pass=>pass.replace(row(8),row(8,4100))))!==null)
 throw Error('Conflicting original contract term accepted');
const {complementEligible}=require('./handset_list_parse');
if(complementEligible([phone[0],phone[1].replace(row(8),row(8,4100))]))
 throw Error('Two different phone contract terms were treated as incomplete');
if(complementImage([row(1)+'\n'+row(2),row(1)+'\n'+row(2)],
  [row(3)+'\n'+row(4),row(3)+'\n'+row(4)])!==null)
 throw Error('Disjoint visual order accepted');
if(complementImage(phone,[row(7)+'\n'+row(8),row(7)+'\n'+row(8)])!==null)
 throw Error('No new row must not masquerade as a complement');
"""
        completed=subprocess.run(['node','-e',script],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)

    def test_incomplete_local_ocr_uses_original_image_for_bounded_complement(self):
        from types import SimpleNamespace
        failure=subprocess.CalledProcessError(1,['node'],stderr='private original')
        counts={'version':1,'uniqueRows':8,'expectedRows':10,'imagesTotal':1,
                'imagesWithRows':1,'conflictingRows':0,'duplicateRows':0,
                'reason':'incomplete'}
        parsed={'items':[{'isin':str(n)} for n in range(10)],'evidence':{'products':[]}}
        responses=[
            SimpleNamespace(stdout=json.dumps([['phone pass a','phone pass b']])),
            failure,
            SimpleNamespace(stdout=json.dumps(counts)),
            SimpleNamespace(stdout='true'),
            SimpleNamespace(stdout=json.dumps([['native 1','native 2','native 3']])),
            SimpleNamespace(stdout=json.dumps(['merged pass a','merged pass b'])),
            SimpleNamespace(stdout=json.dumps(parsed)),
        ]
        payload={'images':[{'png':'saved original screenshot','localOcr':{
            'expectedIsins':['DE000ZZ00016'],
            'passes':[['phone pass a'],['phone pass b']]}}]}
        with patch('evaluator_runtime.run',side_effect=responses) as run:
            result=worker.process(payload,'2026-11-18T18:43:10Z')
        self.assertEqual(run.call_count,7)
        self.assertEqual(json.loads(run.call_args_list[3].kwargs['input'])['mode'],'complement-eligible')
        self.assertIn('--ocr',run.call_args_list[4].args[0])
        self.assertEqual(json.loads(run.call_args_list[4].kwargs['input']),[payload['images'][0]])
        self.assertEqual(json.loads(run.call_args_list[5].kwargs['input'])['mode'],'complement')
        final=json.loads(run.call_args_list[6].kwargs['input'])
        self.assertEqual(final['images'],[['merged pass a','merged pass b']])
        self.assertEqual(final['localSources'],[False])
        self.assertEqual(result['recognitionRoute']['nativeComplementImages'],1)
        self.assertEqual(result['recognitionRoute']['phoneMlKitImages'],1)
        self.assertEqual(len(result['items']),10)

    def test_conflicting_ocr_complement_never_authorizes_missing_rows(self):
        from types import SimpleNamespace
        failure=subprocess.CalledProcessError(1,['node'])
        counts={'version':1,'uniqueRows':8,'expectedRows':10,'imagesTotal':1,
                'imagesWithRows':1,'conflictingRows':0,'duplicateRows':0,
                'reason':'incomplete'}
        answers=[
            SimpleNamespace(stdout=json.dumps([['old pass a','old pass b']])),
            failure,SimpleNamespace(stdout=json.dumps(counts)),
            SimpleNamespace(stdout='false'),
        ]
        with patch('evaluator_runtime.run',side_effect=answers) as run:
            with self.assertRaises(worker.ListVerificationError) as raised:
                worker.process({'images':[{'png':'existing original',
                    'localOcr':{'expectedIsins':['DE000ZZ00016'],'passes':[[],[]]}}]},
                    '2026-11-18T18:43:10Z')
        self.assertEqual(raised.exception.diagnostics,counts)
        self.assertEqual(run.call_count,4)
        self.assertFalse(any('--ocr' in call.args[0] for call in run.call_args_list))
        self.assertNotIn('existing original',str(raised.exception))

    def test_node_verification_diagnoses_missing_ten_without_leaking_text(self):
        input_payload={'mode':'diagnose','images':[
            ['PRIVATE ACCOUNT NOT A PRODUCT', 'PRIVATE ACCOUNT NOT A PRODUCT']],
            'appSources':[False],'localSources':[False]}
        result=subprocess.run(['node','handset_list_parse.js'],
            input=json.dumps(input_payload),text=True,capture_output=True,check=True)
        parsed=json.loads(result.stdout)
        self.assertEqual(parsed['uniqueRows'],0)
        self.assertEqual(parsed['imagesWithRows'],0)
        self.assertEqual(parsed['reason'],'incomplete')
        self.assertNotIn('PRIVATE',result.stdout)
        self.assertEqual(worker.bounded_list_diagnostics(parsed),parsed)

    def test_failed_ocr_parser_uses_a_separate_redacted_diagnosis(self):
        from types import SimpleNamespace
        counts={'version':1,'uniqueRows':6,'expectedRows':10,
                'imagesTotal':1,'imagesWithRows':1,'conflictingRows':0,
                'duplicateRows':0,'reason':'incomplete'}
        calls=[
            SimpleNamespace(stdout='[["incomplete","incomplete"]]'),
            subprocess.CalledProcessError(1,['node'],stderr='private inaccessible data'),
            SimpleNamespace(stdout=json.dumps(counts))
        ]
        with patch('evaluator_runtime.run',side_effect=calls) as run:
            with self.assertRaises(worker.ListVerificationError) as caught:
                worker.process({'images':[{'png':'never decoded in mock'}]},
                               '2026-11-18T09:00:00Z')
        self.assertEqual(caught.exception.diagnostics,counts)
        self.assertEqual(run.call_count,3)
        diagnosis=json.loads(run.call_args_list[2].kwargs['input'])
        self.assertEqual(diagnosis['mode'],'diagnose')
        self.assertNotIn('PRIVATE',json.dumps(caught.exception.diagnostics))

    def test_semantic_path_never_starts_ocr(self):
        from types import SimpleNamespace
        text={'before':['row'],'after':['row']}
        with patch('evaluator_runtime.run',side_effect=[SimpleNamespace(stdout='[["row","row"]]'),SimpleNamespace(stdout='{"items":[]}')]) as run:
            worker.process({'images':[{'png':'private image','appText':text}]},'2026-10-30T12:00:00Z')
        self.assertEqual(run.call_count,2)
        self.assertTrue(all(c.args[0][0]=='node' for c in run.call_args_list))
        self.assertNotIn('private image',run.call_args_list[0].kwargs['input'])
        self.assertEqual(json.loads(run.call_args_list[1].kwargs['input'])['appSources'],[True])

    def test_phone_mlkit_pair_prevents_heavy_server_ocr_and_keeps_source(self):
        from product_quotes import valid_isin
        def identifier(number):
            stem='DE000ZZ'+str(number).zfill(4)
            return next(stem+str(x) for x in range(10) if valid_isin(stem+str(x)))
        def row(number):
            return ('SG Gold Turbo BEST Open-End Call BAR 4000 BP 4000 Bv 10 | '+
                identifier(number)+' Societe Generale OTC EUR')
        images=[]
        for numbers in ([1,2,3,4],[4,5,6,7],[7,8,9,10]):
            lines=[row(n) for n in numbers]
            images.append({'png':'not decoded on semantic fast path',
                           'localOcr':{'expectedIsins':[identifier(n) for n in numbers],
                                       'passes':[lines,lines]}})
        with patch('handset_list_worker.guarded_ocr_run',
                   side_effect=AssertionError('Native OCR was invoked')) as heavy:
            result=worker.process({'images':images},'2026-11-03T08:00:00Z')
        heavy.assert_not_called()
        self.assertEqual(len(result['items']),10)
        self.assertEqual(result['recognitionRoute'],{
            'appTextImages':0,'phoneMlKitImages':3,'serverOcrFallbackImages':0,
            'missingPhoneReadingImages':0,'rejectedPhoneReadingImages':0})
        self.assertTrue(all(x['listRow']['extractionMethod']=='on-device-mlkit-two-scale'
                            for x in result['items']))
        self.assertTrue(all(x['listRow']['crossChecked'] for x in result['items']))
        self.assertTrue(all(x['listRow']['source']=='DEGIRO-Listenbild'
                            for x in result['items']))
        self.assertTrue(all(not x['listRow']['isExecutableQuote'] for x in result['items']))

    def test_mixed_phone_batch_with_optical_ratio_label_never_loads_native_models(self):
        from product_quotes import valid_isin
        def identifier(n):
            stem='DE000ZZ'+str(n).zfill(4)
            return next(stem+str(x) for x in range(10) if valid_isin(stem+str(x)))
        def row(n):
            return f'SG Gold Turbo BEST Open-End Call BAR 4000 BP 3999.25 Bv 10 | {identifier(n)} Societe Generale OTC EUR'
        first=[row(n).replace('Bv 10', 'By 10') for n in range(1,5)]
        second=[row(n).replace('Bv 10', 'By 10' if n != 4 else 'Bv 10') for n in range(1,5)]
        images=[{'png':'must never be decoded', 'localOcr':{
            'expectedIsins':[identifier(n) for n in range(1,5)], 'passes':[first,second]}}]
        for group in ([5,6,7,8,9],[6,7,8,9,10]):
            rows=[row(n) for n in group]
            images.append({'png':'must never be decoded', 'appText':{'before':rows,'after':rows}})
        original=json.dumps(images)
        with patch.object(worker,'guarded_ocr_run',side_effect=AssertionError('Native model started')) as native:
            result=worker.process({'images':images},'2026-11-05T18:10:00Z')
        native.assert_not_called()
        self.assertEqual(result['recognitionRoute'],{
            'appTextImages':2,'phoneMlKitImages':1,'serverOcrFallbackImages':0,
            'missingPhoneReadingImages':0,'rejectedPhoneReadingImages':0})
        self.assertEqual(json.dumps(images),original)
        self.assertEqual(len(result['items']),10)
        self.assertTrue(all(x['listRow']['ratio']==.1 for x in result['items']))
        self.assertTrue(all(not x['listRow']['isExecutableQuote'] for x in result['items']))
        self.assertTrue(all(x['listRow']['extractionMethod']=='on-device-mlkit-two-scale' for x in result['items'][:4]))
        # Two optical values must still agree; label repair cannot fix a number.
        images[0]['localOcr']['passes'][1][0]=second[0].replace('By 10', 'By 100')
        with patch.object(worker,'guarded_ocr_run',side_effect=AssertionError('Native model started')):
            with self.assertRaises(worker.ListVerificationError):
                worker.process({'images':images},'2026-11-05T18:10:00Z')

    def test_positioned_semantic_rows_import_ten_without_native_ocr(self):
        from product_quotes import valid_isin
        def row(number):
            stem='DE000ZZ'+str(number).zfill(4)
            isin=next(stem+str(n) for n in range(10) if valid_isin(stem+str(n)))
            return ('SG Gold Turbo BEST Open-End Call BAR 4000 BP 4000 Bv 10 | '+
                    isin+' Societe Generale OTC EUR')
        images=[]
        for group in ([1,2,3,4],[4,5,6,7],[7,8,9,10]):
            rows=[row(n) for n in group]
            images.append({'png':'original retained but never decoded',
                           'appText':{'before':rows,'after':list(rows)}})
        with patch('handset_list_worker.guarded_ocr_run',
                   side_effect=AssertionError('Native OCR must not start')) as heavy:
            result=worker.process({'images':images},'2026-11-05T08:00:00Z')
        heavy.assert_not_called()
        self.assertEqual(len(result['items']),10)
        self.assertTrue(all(item['listRow']['extractionMethod']=='accessibility-before-after'
                            for item in result['items']))
        self.assertTrue(all(item['listRow']['textCaptureMatched'] for item in result['items']))
        self.assertTrue(all(not item['listRow']['crossChecked'] for item in result['items']))

    def test_raw_local_ocr_glyph_rows_reach_ten_product_parser_without_native_ocr(self):
        from product_quotes import valid_isin
        images=[]
        raw_ids=[]
        for group in ([1,2,3,4],[4,5,6,7],[7,8,9,10]):
            ids=[];rows=[]
            for number in group:
                stem='DE000ZZ'+str(number).zfill(4)
                isin=next(stem+str(n) for n in range(10) if valid_isin(stem+str(n)))
                optical=isin.replace('0','O')
                ids.append(isin);raw_ids.append(optical)
                rows.append('SG Gold Turbo BEST Open-End Call BAR 4000 BP 4000 Bv 10 | '+
                            optical+' Societe Generale OTC EUR')
            images.append({'png':'original retained','localOcr':{'expectedIsins':ids,'passes':[rows,list(rows)]}})
        with patch('handset_list_worker.guarded_ocr_run',side_effect=AssertionError('Native OCR invoked')) as heavy:
            result=worker.process({'images':images},'2026-11-05T08:00:00Z')
        heavy.assert_not_called()
        self.assertEqual(len(result['items']),10)
        self.assertTrue(all(item['listRow']['extractionMethod']=='on-device-mlkit-two-scale' for item in result['items']))
        self.assertTrue(all(item['listRow']['crossChecked'] for item in result['items']))
        self.assertTrue(all(item['originalIsin'] in raw_ids for item in result['items']))

    def test_verified_phone_rows_can_prove_ten_without_native_ocr_for_rejected_image(self):
        from product_quotes import valid_isin
        def identifier(n):
            stem='DE000ZZ'+str(n).zfill(4)
            return next(stem+str(x) for x in range(10) if valid_isin(stem+str(x)))
        def row(n):
            return ('SG Gold Turbo BEST Open-End Call BAR 4000 BP 4000 Bv 10 | '+
                    identifier(n)+' Societe Generale OTC EUR')
        images=[]
        for group in ([1,2,3,4,5,6],[5,6,7,8,9,10]):
            lines=[row(n) for n in group]
            images.append({'png':'original never opened',
                           'appText':{'before':lines,'after':list(lines)}})
        images.append({'png':'unreadable original is retained',
                       'localOcr':{'expectedIsins':['invalid'],'passes':[['bad'],['bad']]}})
        with patch.object(worker,'guarded_ocr_run',
                          side_effect=AssertionError('Native OCR must not launch')) as heavy:
            result=worker.process({'images':images},'2026-11-18T18:37:00Z')
        heavy.assert_not_called()
        self.assertEqual(len(result['items']),10)
        self.assertEqual(len({item['isin'] for item in result['items']}),10)
        self.assertEqual(result['recognitionRoute'],{
            'appTextImages':2,'phoneMlKitImages':0,'serverOcrFallbackImages':0,
            'missingPhoneReadingImages':0,'rejectedPhoneReadingImages':0,
            'skippedUnneededImages':1})
        self.assertEqual(worker.bounded_recognition_route(result['recognitionRoute']),
                         result['recognitionRoute'])
        self.assertTrue(all(item['listRow']['source']=='DEGIRO-App-Text'
                            for item in result['items']))
        self.assertTrue(all(item['listRow']['imageReference'] in
                            ('DEGIRO-TOP10-1.png','DEGIRO-TOP10-2.png')
                            for item in result['items']))
        self.assertTrue(all(not item['listRow']['isExecutableQuote']
                            for item in result['items']))

    def test_missing_tenth_phone_product_never_bypasses_native_memory_guard(self):
        from product_quotes import valid_isin
        def identifier(n):
            stem='DE000ZZ'+str(n).zfill(4)
            return next(stem+str(x) for x in range(10) if valid_isin(stem+str(x)))
        rows=['SG Gold Turbo BEST Open-End Call BAR 4000 BP 4000 Bv 10 | '+
              identifier(n)+' Societe Generale OTC EUR' for n in range(1,10)]
        images=[{'png':'first original','appText':{'before':rows,'after':list(rows)}},
                {'png':'second original'}]
        with patch.object(worker,'guarded_ocr_run',
                          side_effect=worker.OcrMemoryDeferred('Headroom not available')) as heavy:
            with self.assertRaises(worker.OcrMemoryDeferred):
                worker.process({'images':images},'2026-11-18T18:37:00Z')
        heavy.assert_called_once()

    def test_previous_exhausted_memory_receipt_is_eligible_for_resumption(self):
        from types import SimpleNamespace
        queries=[]
        class Db:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def commit(self):pass
            def execute(self,sql,args=()):
                queries.append(sql)
                return SimpleNamespace(fetchone=lambda:None)
        self.assertFalse(worker.tick(lambda:Db()))
        selection=next(q for q in queries if q.startswith('SELECT i.batch_id'))
        self.assertIn("OCR_MEMORY_WAIT_EXHAUSTED",selection)
        self.assertIn("memoryDeferrals",selection)
        self.assertIn("<24",selection)

    def test_only_missing_phone_evidence_goes_to_server_fallback(self):
        from types import SimpleNamespace
        images=[{'png':'image-a','appText':{'before':['safe'], 'after':['safe']}},
                {'png':'image-b'},
                {'png':'image-c','localOcr':{'expectedIsins':['DE000ZZ00016'],'passes':[['r'],['r']]}}]
        responses=[
            SimpleNamespace(stdout=json.dumps([['paired','paired'], None, ['mlkit','mlkit']])),
            subprocess.CalledProcessError(1,['node']),
            SimpleNamespace(stdout=json.dumps([['native-pass-one','native-pass-two']])),
            SimpleNamespace(stdout=json.dumps({'items':[],'evidence':{}})),
        ]
        with patch('evaluator_runtime.run',side_effect=responses) as runner:
            result=worker.process({'images':images},'2026-11-11T08:00:00Z')
        self.assertEqual(runner.call_count,4)
        self.assertEqual(sum('--ocr' in call.args[0] for call in runner.call_args_list),1)
        self.assertEqual(result['recognitionRoute'],{
            'appTextImages':1,'phoneMlKitImages':1,'serverOcrFallbackImages':1,
            'missingPhoneReadingImages':1,'rejectedPhoneReadingImages':0})
        self.assertEqual(images[1],{'png':'image-b'})

    def test_invalid_phone_reading_falls_back_without_claiming_accepted_mlkit(self):
        from types import SimpleNamespace
        image={'png':'original','localOcr':{'expectedIsins':['DE000ZZ00016'],
            'passes':[['contradiction'],['contradiction']]}}
        responses=[
            SimpleNamespace(stdout='[null]'),
            SimpleNamespace(stdout=json.dumps([['one','two']])),
            SimpleNamespace(stdout=json.dumps({'items':[],'evidence':{}})),
        ]
        with patch('evaluator_runtime.run',side_effect=responses):
            result=worker.process({'images':[image]},'2026-11-11T08:00:00Z')
        self.assertEqual(result['recognitionRoute'],{
            'appTextImages':0,'phoneMlKitImages':0,'serverOcrFallbackImages':1,
            'missingPhoneReadingImages':0,'rejectedPhoneReadingImages':1})
        self.assertEqual(image['png'],'original')

    def test_ocr_route_rejects_invalid_counts_and_keeps_old_batches_compatible(self):
        valid={'appTextImages':2,'phoneMlKitImages':1,'serverOcrFallbackImages':1,
               'missingPhoneReadingImages':1,'rejectedPhoneReadingImages':0}
        self.assertIsNone(worker.bounded_recognition_route(None))
        self.assertEqual(worker.bounded_recognition_route(valid),valid)
        augmented={**valid,'nativeComplementImages':1}
        self.assertEqual(worker.bounded_recognition_route(augmented),augmented)
        for invalid in (
            {**valid,'nativeComplementImages':2},
            {**valid,'serverOcrFallbackImages':2},
            {**valid,'missingPhoneReadingImages':0},
            {**valid,'appTextImages':True},
            {**valid,'serverOcrFallbackImages':5},
            {**valid,'accountId':'private'}
        ):
            with self.assertRaises(ValueError):
                worker.bounded_recognition_route(invalid)

    def test_ocr_defers_before_spawn_when_headroom_is_insufficient(self):
        with patch.object(worker,'container_memory_bytes',return_value=309*1024*1024),patch('subprocess.Popen') as spawn:
            with self.assertRaises(worker.OcrMemoryDeferred):
                worker.guarded_ocr_run(['ocr'],input='[]',text=True,capture_output=True,timeout=35,check=True,env={},close_fds=True)
            spawn.assert_not_called()


    def test_505_policy_keeps_196_mib_start_reserve(self):
        from types import SimpleNamespace
        for mib in (309,400,504,505,None):
            used=None if mib is None else mib*1024*1024
            with patch.object(worker,'container_memory_bytes',return_value=used), \
                 patch('memory_watch.release_free_pages'),patch('subprocess.Popen') as spawn:
                with self.assertRaises(worker.OcrMemoryDeferred):
                    worker.guarded_ocr_run(['ocr'],input='[]',text=True,capture_output=True,
                        timeout=35,check=True,env={},close_fds=True)
                spawn.assert_not_called()
        with patch.object(worker,'container_memory_bytes',return_value=306*1024*1024), \
             patch('memory_watch.release_free_pages'),patch('subprocess.Popen') as spawn, \
             patch.object(worker,'wait_ocr',return_value=0):
            result=worker.guarded_ocr_run(['ocr'],input='[]',text=True,capture_output=True,
                timeout=35,check=True,env={},close_fds=True)
            spawn.assert_called_once();self.assertEqual(result.returncode,0)
        self.assertEqual(worker.status()['ocrMemoryLimitMiB'],505)
        self.assertEqual(worker.status()['ocrStartReserveMiB'],196)
        # 308 + 196 stays strictly below the unchanged 505-MiB cutoff.
        with patch.object(worker,'container_memory_bytes',return_value=308*1024*1024), \
             patch('memory_watch.release_free_pages'),patch('subprocess.Popen') as spawn, \
             patch.object(worker,'wait_ocr',return_value=0):
            worker.guarded_ocr_run(['ocr'],input='[]',text=True,capture_output=True,
                timeout=35,check=True,env={},close_fds=True)
            spawn.assert_called_once()


    def test_ocr_can_cross_old_ceiling_but_is_killed_at_505(self):
        class Child:
            args=['ocr'];killed=False
            def poll(self):return None
            def kill(self):self.killed=True
            def wait(self,timeout=None):return -9
        child=Child();samples=iter([480,500,504,505]);observed=[]
        def memory():
            value=next(samples);observed.append(value);return value*1024*1024
        with self.assertRaises(MemoryError):
            worker.wait_ocr(child,memory,clock=lambda:0,sleep=lambda _:None)
        self.assertEqual(observed,[480,500,504,505]);self.assertTrue(child.killed)

    def test_persistence_retries_transient_conflicts_after_transaction_exit(self):
        from types import SimpleNamespace
        from contextlib import contextmanager
        parsed={'items':[{'isin':str(n)} for n in range(10)],'evidence':{'products':[]}}
        events=[]
        class Conflict(Exception):sqlstate='55P03'
        class Conn:
            def execute(self,sql,args=()):
                if sql.startswith('SELECT'):return SimpleNamespace(fetchone=lambda:(None,))
                events.append('write')
            def commit(self):events.append('commit')
        @contextmanager
        def connect():
            events.append('enter')
            try:yield Conn()
            finally:events.append('exit')
        def sleep(delay):
            self.assertEqual(events[-1],'exit')
            events.append('sleep')
        with patch('paper_simulation.sync',side_effect=[Conflict(),{'ok':True,'products':10}]) as sync:
            self.assertEqual(worker.persist_parsed(connect,'a'*32,parsed,sleep),'synced')
            self.assertEqual(sync.call_count,2)
        self.assertEqual(events.count('commit'),1)
        self.assertEqual(events.count('write'),1)
        events.clear()
        with patch('paper_simulation.sync',side_effect=Conflict()) as sync:
            with self.assertRaises(Conflict):worker.persist_parsed(connect,'a'*32,parsed,sleep)
            self.assertEqual(sync.call_count,5)
        self.assertEqual(events.count('sleep'),4)
        self.assertNotIn('commit',events)
        with patch('paper_simulation.sync',side_effect=ValueError('invalid evidence')) as sync:
            with self.assertRaises(ValueError):worker.persist_parsed(connect,'a'*32,parsed,sleep)
            self.assertEqual(sync.call_count,1)

    def test_import_receipt_records_only_bounded_routing_counts(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        route={'appTextImages':2,'phoneMlKitImages':1,'serverOcrFallbackImages':0,
               'missingPhoneReadingImages':0,'rejectedPhoneReadingImages':0}
        parsed={'items':[{'isin':str(n)} for n in range(10)],
                'evidence':{'products':[]},'recognitionRoute':route}
        written=[]
        class Conn:
            def execute(self,sql,args=()):
                if sql.startswith('SELECT'): return SimpleNamespace(fetchone=lambda:(None,))
                written.append((sql,args))
            def commit(self): pass
        @contextmanager
        def connect():
            yield Conn()
        with patch('paper_simulation.sync',return_value={'ok':True,'products':10}):
            self.assertEqual(worker.persist_parsed(connect,'f'*32,parsed),'synced')
        self.assertEqual(len(written),1)
        receipt=json.loads(written[0][1][1])
        self.assertEqual(receipt['recognitionRoute'],route)
        self.assertEqual(receipt['stage'],'synced')
        self.assertNotIn('images',receipt)
        self.assertNotIn('account',str(receipt).lower())

    def test_strip_context_overlaps_but_line_ownership_never_doubles(self):
        for height in (1,511,512,513,896,897,1536,2400,3200):
            strips=list(worker.ocr_strips(height))
            self.assertEqual(strips[0][0],0)
            self.assertEqual(strips[-1][1],height)
            for top,bottom,lower,upper in strips:
                self.assertLessEqual(bottom-top,512)
                self.assertLessEqual(top,lower)
                self.assertLessEqual(upper,bottom)
            for before,after in zip(strips,strips[1:]):
                self.assertEqual(before[3],after[2])
                self.assertGreaterEqual(before[1]-after[0],128)
            for y in range(height):
                self.assertEqual(sum(lo<=y<hi for _,_,lo,hi in strips),1)

    def test_ocr_child_is_killed_before_shared_container_limit(self):
        class Child:
            args=['ocr']
            returncode=None
            killed=False
            waited=False
            def poll(self):return self.returncode
            def kill(self):self.killed=True;self.returncode=-9
            def wait(self,timeout=None):self.waited=timeout;return self.returncode
        child=Child()
        with self.assertRaises(MemoryError):
            worker.wait_ocr(child,lambda:worker.OCR_CONTAINER_LIMIT,clock=lambda:0,sleep=lambda _:None)
        self.assertTrue(child.killed);self.assertEqual(child.waited,5)
        child=Child()
        with self.assertRaises(RuntimeError):
            worker.wait_ocr(child,lambda:None,clock=lambda:0,sleep=lambda _:None)
        self.assertTrue(child.killed)

    def test_ocr_images_share_admission_and_release_between_images(self):
        from types import SimpleNamespace
        with patch('evaluator_runtime.run',side_effect=[
            SimpleNamespace(stdout='[["a","a","a"]]'),
            SimpleNamespace(stdout='[["b","b","b"]]'),
            SimpleNamespace(stdout='{"items":[]}')]) as run:
            worker.process({'images':[{'png':'one'},{'png':'two'}]},'2026-10-29T20:00:00Z')
        self.assertEqual(run.call_count,3)
        for call in run.call_args_list[:2]:
            self.assertEqual(len(json.loads(call.kwargs['input'])),1)
            self.assertEqual(call.kwargs['priority'],2)
            self.assertEqual(call.kwargs['timeout'],35)
            self.assertTrue(call.kwargs['close_fds'])
        self.assertEqual(run.call_args_list[-1].args[0][0],'node')

    def test_alt_ocr_is_used_only_for_locally_tagged_retry(self):
        from types import SimpleNamespace
        def outputs():
            return [SimpleNamespace(stdout='[["a","a","a"]]'),
                    SimpleNamespace(stdout='{"items":[]}')]
        base={'images':[{'png':'not transmitted'}]}
        for payload, expected in ((base,False),
                (dict(base,_ocr_mode='enhanced'),True)):
            with patch('evaluator_runtime.run',side_effect=outputs()) as run:
                worker.process(payload,'2026-10-31T19:13:55Z')
            command=run.call_args_list[0].args[0]
            self.assertEqual('--enhanced' in command,expected)
            self.assertEqual(command[2],'--ocr')
            self.assertEqual(len(json.loads(run.call_args_list[0].kwargs['input'])),1)

    def test_list_verification_failure_gets_one_bounded_alternate_try(self):
        class Result:
            def __init__(self,value):self.value=value
            def fetchone(self):return self.value
        class DB:
            def __init__(self,attempts,error,memory=0,pending=False):
                self.attempts=attempts;self.error=error
                self.memory=memory;self.pending=pending;self.writes=[]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def commit(self):pass
            def execute(self,sql,args=()):
                if sql.startswith('SELECT i.batch_id'):
                    return Result(('a'*32,{'images':[{'at':'2026-10-31T19:13:55Z'}]},
                        None,self.attempts,{'stage':'read-failed','error':self.error,
                            'memoryDeferrals':self.memory,'enhancedPending':self.pending}))
                if sql.startswith('SELECT i.import_receipt'):return Result((None,))
                if 'import_receipt=%s' in sql:self.writes.append(json.loads(args[0]))
                return Result(None)
        def attempt(attempts,error,memory=0,pending=False):
            db=DB(attempts,error,memory,pending);calls=[]
            def runner(payload,at):
                calls.append(payload.get('_ocr_mode'))
                raise worker.ListVerificationError('Do not log private OCR text')
            worker.tick(lambda:db,runner)
            self.assertEqual(db.writes[-1]['error'],'ListVerificationError')
            return calls
        self.assertEqual(attempt(3,'ListVerificationError'),['enhanced'])
        self.assertEqual(attempt(1,'ListVerificationError'),['enhanced'])
        self.assertEqual(attempt(2,'ListVerificationError'),['enhanced'])
        self.assertEqual(attempt(3,'OcrChildError'),[None])
        self.assertEqual(attempt(4,'ListVerificationError'),[None])
        self.assertEqual(attempt(7,'ListVerificationError',memory=4),['enhanced'])
        self.assertEqual(attempt(7,'ListVerificationError'),[None])
        self.assertEqual(attempt(7,'OcrMemoryDeferred',memory=5,pending=True),['enhanced'])

    def test_phone_ocr_size_is_bounded_without_changing_original(self):
        for width,height in [(1080,2400),(1440,3200),(5000,3000),(709,1536)]:
            for scale in (.85,1,2.5):
                w,h=worker.ocr_size(width,height,scale)
                self.assertLessEqual(w,1200)
                self.assertLessEqual(w*h,1602500)
                self.assertAlmostEqual(w/h,width/height,delta=.002)

    def test_worker_status_reports_queue_failure_without_private_error_text(self):
        def broken():raise RuntimeError('private database information')
        with patch('video_ocr.tick', return_value='idle'), patch('handset_list_worker.time.sleep',side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):worker.loop(broken)
        result=worker.status()
        self.assertEqual(result['state'],'queue-error')
        self.assertEqual(result['error'],'RuntimeError')
        self.assertTrue(result['fresh'])
        self.assertNotIn('private',json.dumps(result))


    def test_shared_parser_requires_ten_agreed_rows_and_preserves_quote_gaps(self):
        script=r'''
const {parse,normalizeLayout,appImage}=require('./handset_list_parse');
const fs=require('fs'),vm=require('vm'),c={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),c);
const valid=c.window.BobDegiro.validIsin;
function id(n){const prefix='DE000ZZ'+String(n).padStart(4,'0');for(let i=0;i<10;i++)if(valid(prefix+i))return prefix+i;}
function row(n,bar=4000){return `SG Gold Turbo BEST Open-End Call BAR ${bar} BP ${bar} Bv 10 | ${id(n)}\nSociete Generale OTC EUR K V`;}
const images=[[1,2,3,4],[4,5,6,7],[7,8,9,10]].map(ns=>{let t=ns.map(n=>row(n)).join('\n');return [t,t];});
const out=parse(images,'2026-10-29T19:00:00Z');
const compact=images.map(passes=>passes.map(t=>t.replaceAll('SG Gold Turbo BEST Open-End Call BAR','SGGoldTurboBESTOpen-EndCallBAR')));
if(parse(compact,'2026-10-29T19:00:00Z').items.length!==10)throw Error('Compact label boundaries');
if(normalizeLayout('BAR4400BP4400Bv\n1019/03/2027|')!=='BAR4400BP4400Bv\n10 19/03/2027|')throw Error('Compact ratio date');
if(normalizeLayout('Bv 1019/03/2027 |')!=='Bv 10 19/03/2027 |')throw Error('Ratio date separator');
if(normalizeLayout('BNPGOLDMiniLongSL3690.3449STR3617.9852 R 10')!=='BNP GOLD Mini Long SL3690.3449STR3617.9852 R 10')throw Error('BNP label boundaries');
if(normalizeLayout('DE000ZZ00001 3970.33')!=='DE000ZZ00001 3970.33')throw Error('Identity or numbers changed');

if(out.items.length!==10||out.evidence.products.some(p=>p.price!==null||p.isinConfirmed!==false||!p.listVenueEvidence))throw Error('Evidence boundaries');
for(const invalid of [images.slice(0,2),images.map(p=>p.slice(0,1)),[...images,[row(4,4100),row(4,4100)]]]){
 let rejected=false;try{parse(invalid,'2026-10-29T19:00:00Z')}catch(_){rejected=true}if(!rejected)throw Error('Unsafe list');
}
const app=images.map(p=>({before: p[0].split(/\n(?=SG Gold)/),after:p[0].split(/\n(?=SG Gold)/)}));
const direct=parse(app.map(appImage),'2026-10-29T19:00:00Z',[true,true,true]);
if(direct.items.length!==10||direct.items.some(i=>i.listRow.source!=='DEGIRO-App-Text'||i.listRow.crossChecked)||direct.evidence.products.some(p=>p.listVenueEvidence||p.quote||p.price))throw Error('App provenance or approval');
for(const bad of [{before:[row(1)],after:[row(2)]},{before:[row(1),row(1)],after:[row(1),row(1)]},{before:['bad'],after:['bad']}])if(appImage(bad)!==null)throw Error('Bad semantic text');
console.log(JSON.stringify(out));
'''
        result=subprocess.run(['node','-e',script],text=True,capture_output=True,check=True)
        parsed=json.loads(result.stdout)
        self.assertEqual(len(parsed['items']),10)
        rows=[i['name']+' | '+i['isin']+'\n'+i['listRow']['venue']+' '+i['listRow']['currency'] for i in parsed['items']]
        # Run the actual subprocess protocol end to end. Invalid PNG data proves
        # that a complete semantic capture never invokes the image decoder.
        imported=worker.process({'images':[{'png':'not decoded','appText':{'before':rows,'after':rows}}]},'2026-10-29T19:00:00Z')
        self.assertEqual(len(imported['items']),10)
        self.assertTrue(all(i['listRow']['source']=='DEGIRO-App-Text' for i in imported['items']))

    def test_worker_ack_only_after_persistence_and_keeps_failed_batch(self):
        class Result:
            def __init__(self,value):self.value=value
            def fetchone(self):return self.value
        class DB:
            def __init__(self):self.receipts=[];self.commits=0
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def commit(self):self.commits+=1
            def execute(self,sql,args=()):
                if sql.startswith('SELECT i.batch_id'):return Result(('a'*32,{'images':[{'at':'2026-10-29T19:00:00Z'}]},None,0,None))
                if sql.startswith('SELECT i.import_receipt'):return Result((None,))
                if 'processing_attempts=processing_attempts+1' in sql:self.receipts.append(json.loads(args[0]))
                if 'SET parsed_items=' in sql:self.receipts.append(json.loads(args[1]))
                if 'SET import_receipt=%s' in sql:self.receipts.append(json.loads(args[0]))
                return Result(None)
        db=DB()
        with patch('paper_simulation.sync',return_value={'ok':True,'products':10}) as sync:
            worker.tick(lambda:db,lambda p,at:{'items':[{'isin':str(n)} for n in range(10)],'evidence':{'listUploadedAt':at,'products':[{'isin':str(n)} for n in range(10)]}})
            self.assertTrue(sync.called);self.assertEqual(db.receipts[0]['stage'],'reading');self.assertEqual(db.receipts[-1]['stage'],'synced');self.assertEqual(db.commits,2)
        db=DB()
        def fail(*_):raise ValueError('private image text must never leak')
        worker.tick(lambda:db,fail)
        self.assertEqual(db.receipts[-1]['stage'],'read-failed')
        self.assertNotIn('private',json.dumps(db.receipts))

class DatabaseTests(unittest.TestCase):
    def test_committed_receipt_owned_by_paired_device(self):
        import os, uuid, time, copy
        from datetime import datetime, timezone
        from contextlib import contextmanager
        url=os.environ.get('BOB_TEST_DATABASE_URL')
        if not url:self.skipTest('CI PostgreSQL not configured')
        import psycopg
        import android_telemetry, android_remote, android_list
        from test_android_list import batch
        schema='handset_'+uuid.uuid4().hex
        with psycopg.connect(url) as admin:
            admin.execute('CREATE SCHEMA '+schema)
        @contextmanager
        def connect():
            with psycopg.connect(url) as conn:
                conn.execute('SET search_path TO '+schema)
                yield conn
        try:
            now=int(time.time());value=batch()
            for i,image in enumerate(value['images']):image['at']=datetime.fromtimestamp(now-10+i,timezone.utc).isoformat()
            with connect() as conn:
                android_telemetry.init(conn);android_remote.init(conn)
                conn.execute('CREATE TABLE bob_paper_products(id INTEGER PRIMARY KEY,payload JSONB)')
                for token in ('a'*64,'b'*64):
                    android_telemetry.handle(conn,{'action':'register','tokenHash':android_telemetry.token_hash(token)})
                state={'sessionId':value['sessionId'],'active':True,'expiresAt':now+900,'seenAt':now}
                conn.execute('INSERT INTO bob_android_remote VALUES(%s,%s::jsonb)',(android_telemetry.token_hash('a'*64),json.dumps(state)))
                android_list.handle(conn,{'action':'list-upload','token':'a'*64,'value':value},now)
                conn.execute("UPDATE bob_android_list_images SET processing_attempts=3,processing_at=now()-interval '5 minutes' WHERE batch_id=%s",(value['batchId'],))
            products=[{'isin':str(n),'name':'test'} for n in range(10)]
            parsed={'items':products,'evidence':{'products':products,'listUploadedAt':value['images'][-1]['at']}}
            def sync(conn,payload):
                conn.execute('INSERT INTO bob_paper_products VALUES(1,%s::jsonb)',(json.dumps(payload),))
                return {'ok':True,'products':10}
            with patch('paper_simulation.sync',side_effect=sync):worker.tick(connect,lambda *_:parsed)
            with connect() as conn:
                own=android_list.handle(conn,{'action':'list-status','token':'a'*64,'value':{'batchId':value['batchId']}},now)
                other=android_list.handle(conn,{'action':'list-status','token':'b'*64,'value':{'batchId':value['batchId']}},now)
                self.assertEqual(own['import']['stage'],'synced')
                self.assertEqual(conn.execute('SELECT processing_attempts FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0],4)
                self.assertIsNone(other['import']);self.assertEqual(other['detailIsins'],[])
                android_list.handle(conn,{'action':'list-receipt','value':{'batchId':value['batchId'],'stage':'reading','count':0}},now)
                again=android_list.handle(conn,{'action':'list-status','token':'a'*64,'value':{'batchId':value['batchId']}},now)
                self.assertEqual(again['import']['stage'],'synced','late browser receipt cannot undo confirmation')
                conn.execute("UPDATE bob_android_list_images SET processing_attempts=4,processing_at=now()-interval '5 minutes',import_receipt=%s::jsonb WHERE batch_id=%s",
                    (json.dumps({'stage':'read-failed','error':'MemoryError'}),value['batchId']))
            with patch('paper_simulation.sync',return_value={'ok':True,'products':10}):
                self.assertTrue(worker.tick(connect,lambda *_:parsed))
            with connect() as conn:
                self.assertEqual(conn.execute('SELECT processing_attempts FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0],5)
                conn.execute("UPDATE bob_android_list_images SET processing_at=now()-interval '5 minutes',import_receipt=%s::jsonb WHERE batch_id=%s",
                    (json.dumps({'stage':'read-failed','error':'MemoryError'}),value['batchId']))
            self.assertFalse(worker.tick(connect,lambda *_:self.fail('Unbounded memory retry')))
            # A completed first failure is eligible promptly, but a live
            # processing lease and other failure types keep the old delay.
            observed=[]
            def enhanced_runner(payload,at):
                observed.append(payload.get('_ocr_mode'))
                raise worker.ListVerificationError('Private source text must not leak')
            for stage,error,age,eligible in [
                ('reading','ListVerificationError',45,False),
                ('read-failed','OcrChildError',45,False),
                ('read-failed','ListVerificationError',10,False),
                ('read-failed','ListVerificationError',45,True)]:
                with connect() as conn:
                    conn.execute("UPDATE bob_android_list_images SET processing_attempts=1,processing_at=now()-(%s * interval '1 second'),import_receipt=%s::jsonb WHERE batch_id=%s",
                        (age,json.dumps({'stage':stage,'error':error}),value['batchId']))
                self.assertEqual(worker.tick(connect,enhanced_runner),eligible)
            self.assertEqual(observed,['enhanced'])
            with connect() as conn:
                row=conn.execute("SELECT processing_attempts,import_receipt FROM bob_android_list_images WHERE batch_id=%s",(value['batchId'],)).fetchone()
                self.assertEqual(row[0],2)
                self.assertTrue(row[1]['enhancedVerification'])
                self.assertNotIn('Private',json.dumps(row[1]))
                conn.execute("UPDATE bob_android_list_images SET processing_at=now()-interval '5 minutes' WHERE batch_id=%s",(value['batchId'],))
            self.assertFalse(worker.tick(connect,lambda *_:self.fail('No repeated enhanced verification')))
            # A previous run with exactly three failed ten-row validations
            # may use one enhanced pass; a fourth such failure terminates.
            with connect() as conn:
                conn.execute("UPDATE bob_android_list_images SET processing_attempts=3,processing_at=now()-interval '5 minutes',import_receipt=%s::jsonb WHERE batch_id=%s",
                    (json.dumps({'stage':'read-failed','error':'ListVerificationError'}),value['batchId']))
            observed=[]
            def enhanced_runner(payload,at):
                observed.append(payload.get('_ocr_mode'))
                raise worker.ListVerificationError('Not enough complete distinct rows')
            self.assertTrue(worker.tick(connect,enhanced_runner))
            self.assertEqual(observed,['enhanced'])
            with connect() as conn:
                state=conn.execute("SELECT processing_attempts,import_receipt->>'error' FROM bob_android_list_images WHERE batch_id=%s",(value['batchId'],)).fetchone()
                self.assertEqual(state,(4,'ListVerificationError'))
            self.assertFalse(worker.tick(connect,lambda *_:self.fail('No fifth OCR verification attempt')))
            with connect() as conn:
                conn.execute("UPDATE bob_android_list_images SET processing_attempts=5,processing_at=now()-interval '5 minutes',import_receipt=%s::jsonb WHERE batch_id=%s",
                    (json.dumps({'stage':'read-failed','error':'LockNotAvailable'}),value['batchId']))
                conn.execute('CREATE TABLE retry_probe(id INTEGER PRIMARY KEY)')
            calls=[]
            def transient_sync(conn,payload):
                conn.execute('INSERT INTO retry_probe VALUES(1)')
                calls.append(1)
                if len(calls)==1:raise psycopg.errors.LockNotAvailable('test conflict')
                return {'ok':True,'products':10}
            with patch('paper_simulation.sync',side_effect=transient_sync):
                self.assertTrue(worker.tick(connect,lambda *_:parsed))
            self.assertEqual(len(calls),2,'failed transaction must roll back its first insert')
            with connect() as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM retry_probe').fetchone()[0],1)
                self.assertEqual(conn.execute('SELECT processing_attempts FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0],6)
                self.assertEqual(android_list.handle(conn,{'action':'list-status','token':'a'*64,'value':{'batchId':value['batchId']}},now)['import']['stage'],'synced')

            # Sustained admission pressure must finish across worker restarts,
            # not reset processing_attempts forever. Original payload survives.
            with connect() as conn:
                conn.execute("UPDATE bob_android_list_images SET processing_attempts=0,processing_at=NULL,import_receipt=NULL WHERE batch_id=%s",(value['batchId'],))
            def deferred(*_):raise worker.OcrMemoryDeferred('private text')
            for count in range(1,25):
                self.assertTrue(worker.tick(connect,deferred))
                with connect() as conn:
                    receipt,attempts,payload=conn.execute('SELECT import_receipt,processing_attempts,payload FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()
                    self.assertEqual(receipt['memoryDeferrals'],count)
                    self.assertEqual(attempts,0 if count<24 else 6)
                    self.assertEqual(payload['images'],value['images'])
                    # Late browser receipts cannot reset the durable budget.
                    android_list.handle(conn,{'action':'list-receipt','value':{'batchId':value['batchId'],'stage':'reading','count':0}},now)
                    after=conn.execute('SELECT import_receipt FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0]
                    self.assertEqual(after['memoryDeferrals'],count)
                    if count==24:self.assertEqual(after,receipt)
                    conn.execute("UPDATE bob_android_list_images SET processing_at=now()-interval '5 minutes' WHERE batch_id=%s",(value['batchId'],))
            self.assertFalse(worker.tick(connect,lambda *_:self.fail('Exhausted memory retries must stop')))
            # A pre-fix batch at four deferrals is now eligible for reprocessing
            # without recapturing or relaxing evidence verification.
            legacy={'batchId':value['batchId'],'stage':'read-failed','count':0,
                    'error':'MemoryError','reason':'OCR_MEMORY_WAIT_EXHAUSTED',
                    'retryAllowed':False,'memoryDeferrals':4}
            with connect() as conn:
                conn.execute("UPDATE bob_android_list_images SET import_receipt=%s::jsonb,processing_attempts=6,processing_at=now()-interval '5 minutes' WHERE batch_id=%s",
                    (json.dumps(legacy),value['batchId']))
            # The mock schema intentionally lacks the production paper tables.
            # Test durable receipt recovery here; paper persistence was already
            # exercised above using a separate explicit transaction test.
            with patch('paper_simulation.sync',return_value={'ok':True,'products':10}):
                self.assertTrue(worker.tick(connect,lambda *_:parsed))
            with connect() as conn:
                final=conn.execute('SELECT import_receipt FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0]
                self.assertIn(final['stage'],('synced','superseded'))
                self.assertEqual(final['count'],10)
            # This is the real reported sequence: memory-deferrals 4,
            # successful first OCR at lifetime attempt 7, only 8 verified
            # rows. The next, enhanced OCR is permitted exactly once.
            incomplete={'batchId':value['batchId'],'stage':'read-failed',
                        'count':0,'error':'ListVerificationError',
                        'enhancedVerification':False,'memoryDeferrals':4,
                        'verificationCounts':{'version':1,'uniqueRows':8,
                            'expectedRows':10,'imagesTotal':3,'imagesWithRows':3,
                            'conflictingRows':0,'duplicateRows':1,'reason':'incomplete'}}
            with connect() as conn:
                conn.execute("UPDATE bob_android_list_images SET import_receipt=%s::jsonb,processing_attempts=7,processing_at=now()-interval '5 minutes' WHERE batch_id=%s",
                    (json.dumps(incomplete),value['batchId']))
            enhanced_calls=[]
            def high_attempt_runner(payload,at):
                enhanced_calls.append(payload.get('_ocr_mode'))
                raise worker.ListVerificationError('Still only eight accepted rows')
            self.assertTrue(worker.tick(connect,high_attempt_runner))
            self.assertEqual(enhanced_calls,['enhanced'])
            with connect() as conn:
                final=conn.execute('SELECT import_receipt FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0]
                self.assertEqual(final['error'],'ListVerificationError')
                self.assertTrue(final['enhancedVerification'])
                conn.execute("UPDATE bob_android_list_images SET processing_at=now()-interval '5 minutes' WHERE batch_id=%s",(value['batchId'],))
            self.assertFalse(worker.tick(connect,lambda *_:self.fail('Enhanced OCR must remain one-shot')))
            # Previously terminal 8-of-10 enhanced runs are given exactly ONE
            # complementary OCR replay, preserving their same original images.
            old={'stage':'read-failed','error':'ListVerificationError',
                 'enhancedVerification':True,'memoryDeferrals':0,
                 'verificationCounts':{'version':1,'uniqueRows':8,'expectedRows':10,
                    'imagesTotal':3,'imagesWithRows':3,'conflictingRows':0,
                    'duplicateRows':1,'reason':'incomplete'}}
            with connect() as conn:
                conn.execute("UPDATE bob_android_list_images SET import_receipt=%s::jsonb,processing_attempts=2,processing_at=now()-interval '5 minutes' WHERE batch_id=%s",
                    (json.dumps(old),value['batchId']))
            observed=[]
            def replay(payload,at):
                observed.append(payload.get('_ocr_mode'))
                raise worker.ListVerificationError('Eight complete verified rows')
            self.assertTrue(worker.tick(connect,replay))
            self.assertEqual(observed,['enhanced'])
            with connect() as conn:
                receipt=conn.execute('SELECT import_receipt FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0]
                self.assertEqual(receipt['complementRecovery'],'phone-native-v1')
                self.assertTrue(receipt['enhancedVerification'])
                conn.execute("UPDATE bob_android_list_images SET processing_at=now()-interval '5 minutes' WHERE batch_id=%s",(value['batchId'],))
            self.assertFalse(worker.tick(connect,lambda *_:self.fail('No second complementary replay')))

        finally:
            with psycopg.connect(url) as admin:admin.execute('DROP SCHEMA '+schema+' CASCADE')

if __name__=='__main__':unittest.main()
