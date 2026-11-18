"""No-model concurrent immutable-file publication; no professional approvals are synthesized."""
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('immutable_publication_evidence',Path(__file__).resolve().parents[1]/'src/base/tools/review_evidence.py')
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


if __name__=='__main__':unittest.main()
