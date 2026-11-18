"""No-model concurrent immutable-file publication; no professional approvals are synthesized."""
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
import sys
import os
from types import SimpleNamespace
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('immutable_publication_evidence',Path(os.environ.get('MATRIX_EVIDENCE_SOURCE',Path(__file__).resolve().parents[1]/'src/base/tools/review_evidence.py')))
evidence=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(evidence)


class ImmutablePublication(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.name='management/stage-reviews/synthetic-token/state.json'
        self.payload=json.dumps({'synthetic':True,'data':'x'*200000},sort_keys=True)

    def test_existing_identical_bytes_are_never_rewritten(self):
        original=evidence.publish_immutable(self.root,self.name,self.payload)
        target=self.root/self.name;before=target.stat()
        with patch.object(evidence.tempfile,'NamedTemporaryFile',side_effect=AssertionError('must not create or truncate an existing file')):
            self.assertEqual(evidence.publish_immutable(self.root,self.name,self.payload.encode()),original)
        after=target.stat()
        self.assertEqual((before.st_ino,before.st_mtime_ns),(after.st_ino,after.st_mtime_ns))
        with self.assertRaisesRegex(ValueError,'immutable file differs'):
            evidence.publish_immutable(self.root,self.name,'different bytes')
        self.assertEqual(target.read_text(),self.payload)

    def test_concurrent_publishers_and_reader_only_observe_complete_bytes(self):
        ready=threading.Event();published=threading.Event();target=self.root/self.name
        def publish():
            ready.wait()
            result=evidence.publish_immutable(self.root,self.name,self.payload)
            published.set()
            for _ in range(12):self.assertEqual(evidence.publish_immutable(self.root,self.name,self.payload),result)
            return result
        def read():
            ready.wait();published.wait()
            for _ in range(200):
                self.assertEqual(evidence.file(self.root,self.name).read_text(),self.payload)
                self.assertTrue(json.loads(target.read_text())['synthetic'])
        with ThreadPoolExecutor(max_workers=9) as pool:
            writers=[pool.submit(publish) for _ in range(8)]
            reader=pool.submit(read);ready.set()
            results=[future.result(timeout=15) for future in writers];reader.result(timeout=15)
        self.assertTrue(all(result==results[0] for result in results))
        self.assertEqual(target.stat().st_nlink,1)
        self.assertFalse(list(target.parent.glob('*.publish')))

    def test_competing_different_payloads_never_overwrite_the_winner(self):
        barrier=threading.Barrier(2)
        def publish(payload):
            barrier.wait()
            try:return evidence.publish_immutable(self.root,self.name,payload)
            except ValueError as error:return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(publish,value) for value in ('first complete bytes','other complete bytes')]
            results=[future.result(timeout=5) for future in futures]
        self.assertEqual(sum(isinstance(value,dict) for value in results),1)
        self.assertEqual(sum(isinstance(value,str) and 'immutable' in value for value in results),1)
        self.assertIn((self.root/self.name).read_text(),('first complete bytes','other complete bytes'))

    def test_unsafe_aliases_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'project-relative'):
            evidence.publish_immutable(self.root,'../escape','bytes')
        directory=self.root/'outside';directory.mkdir()
        (self.root/'alias').symlink_to(directory,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'unsafe immutable'):
            evidence.publish_immutable(self.root,'alias/new.json','bytes')
        target=self.root/'existing.json';target.write_text('original')
        (self.root/'alias.json').symlink_to(target)
        with self.assertRaisesRegex(ValueError,'unsafe'):
            evidence.publish_immutable(self.root,'alias.json','original')

    def test_import_and_read_without_fcntl_do_not_require_a_lock_backend(self):
        with patch.dict(sys.modules,{'fcntl':None,'msvcrt':None}):
            spec=importlib.util.spec_from_file_location('evidence_no_platform_lock',SPEC.origin)
            portable=importlib.util.module_from_spec(spec);spec.loader.exec_module(portable)
            (self.root/'input.txt').write_text('readable')
            self.assertEqual(portable.file(self.root,'input.txt').read_text(),'readable')
            with self.assertRaisesRegex(ValueError,'supported file-lock backend'):
                portable.publish_immutable(self.root,self.name,self.payload)
        self.assertFalse((self.root/self.name).exists())

    def test_public_gate_direction_and_pm_modules_load_without_fcntl(self):
        source=Path(SPEC.origin).parents[2]
        with patch.dict(sys.modules,{'fcntl':None}):
            for relative in ('base/tools/stage_gate.py','base/tools/tone_contract.py','base/tools/review_evidence.py',
                             'orchestration/tools/pm_tasks.py','orchestration/tools/pm_direction.py'):
                with self.subTest(module=relative):
                    spec=importlib.util.spec_from_file_location('portable_'+Path(relative).stem,source/relative)
                    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

    @unittest.skipIf(evidence.fcntl is None,'POSIX-backed Windows API simulation')
    def test_windows_lock_path_keeps_concurrent_publication_immutable(self):
        # Exercise the actual fallback control flow with OS-backed locking on this
        # host. This is not a claim that native Windows has been executed.
        native=evidence.fcntl
        def locking(fd,operation,count):
            self.assertEqual(count,1)
            self.assertEqual(evidence.os.lseek(fd,0,evidence.os.SEEK_CUR),0)
            native.flock(fd,native.LOCK_EX if operation==1 else native.LOCK_UN)
        windows=SimpleNamespace(LK_LOCK=1,LK_UNLCK=0,locking=locking)
        with patch.object(evidence,'fcntl',None),patch.dict(sys.modules,{'msvcrt':windows}):
            self.test_concurrent_publishers_and_reader_only_observe_complete_bytes()
            with self.assertRaisesRegex(ValueError,'immutable file differs'):
                evidence.publish_immutable(self.root,self.name,'cannot replace')
            self.assertEqual(evidence.publish_immutable(self.root,self.name,self.payload)['path'],self.name)

    def test_windows_lock_failure_does_not_publish_unprotected(self):
        def unavailable(*args):
            raise OSError('lock unavailable')
        windows=SimpleNamespace(LK_LOCK=1,LK_UNLCK=0,locking=unavailable)
        with patch.object(evidence,'fcntl',None),patch.dict(sys.modules,{'msvcrt':windows}):
            with self.assertRaisesRegex(OSError,'lock unavailable'):
                evidence.publish_immutable(self.root,self.name,self.payload)
        self.assertFalse((self.root/self.name).exists())

    @unittest.skipIf(evidence.fcntl is None,'POSIX-backed Windows API simulation')
    def test_stage_check_without_fcntl_publishes_a_replayable_receipt(self):
        from practice_fixture import direction,put
        native=evidence.fcntl
        windows=SimpleNamespace(LK_LOCK=1,LK_UNLCK=0,
            locking=lambda fd,op,count:native.flock(fd,native.LOCK_EX if op==1 else native.LOCK_UN))
        with patch.dict(sys.modules,{'fcntl':None,'msvcrt':windows}):
            spec=importlib.util.spec_from_file_location('portable_stage_check',Path(SPEC.origin).with_name('stage_gate.py'))
            gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
            contract,_=direction(self.root,gate.tone)
            artifact=put(self.root,'plan.md','Synthetic current technical intake')
            state=dict(role='solution',current='E-2.1',next='E-2.2',scope=['workspace'],blockers=[],
                artifacts=[artifact],tone_contract=contract,
                conversation_check=put(self.root,'conversation.md','E-2.1->E-2.2')['path'])
            result=gate.check(self.root,state)
            self.assertTrue(result['allowed'])
            view,_=gate.tone.evidence.stage_receipt(self.root,result['review_bundle'])
            self.assertTrue((view/result['upstream_state']).is_file())


if __name__=='__main__':unittest.main()
