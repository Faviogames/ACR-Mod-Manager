"""Manual startup and no-copy level backups; these tests never touch installed mods."""
import json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import test_content
import wr_content_transaction as tx
from wr_content_app import Engine,unregistered_packages

class ManualAndBackupTests(unittest.TestCase):
 def test_startup_does_not_instantiate_manager_or_scan(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);config=root/'manager.json'
   config.write_text(json.dumps(dict(mods=str(root/'mods'),disabled=str(root/'disabled'),state=str(root/'state'),game_paks=str(root/'Paks'))))
   engine=Engine(config)
   with patch('wr_content_app.Manager',side_effect=AssertionError('Startup must not inspect packages')):
    engine.start('load');deadline=time.monotonic()+3
    while engine.state()['busy'] and time.monotonic()<deadline:time.sleep(.01)
   state=engine.state();self.assertFalse(state['busy']);self.assertFalse(state['scanned']);self.assertFalse(state['synced']);self.assertIsNone(state['error'])

 def test_unknown_author_is_shown_and_not_activated_by_manager(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for ext in ('.pak','.utoc','.ucas'):(root/('pakchunk88-OtherAuthor_P'+ext)).write_bytes(b'unknown')
   rows=unregistered_packages(root,True,registered=[])
   self.assertEqual(len(rows),1);self.assertFalse(rows[0]['valid']);self.assertTrue(rows[0]['registration_required']);self.assertEqual(rows[0]['reason'],'No soportado');self.assertTrue(rows[0]['external'])

 def test_manual_foreign_import_reports_the_package_without_copying_it(self):
  from types import SimpleNamespace
  from wr_content_catalog import prepare_incoming
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);file=root/'pakchunk88-OtherAuthor_P.utoc';file.write_bytes(b'unknown')
   with self.assertRaisesRegex(ValueError,'Mod externo no soportado: pakchunk88-OtherAuthor_P.utoc'):
    prepare_incoming(SimpleNamespace(state=root),root,{},root/'out')
   self.assertEqual(file.read_bytes(),b'unknown');self.assertFalse((root/'out').exists())

 def test_large_move_and_recovery_use_links_not_payload_copies(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);mods=root/'mods';disabled=root/'disabled';state=root/'state';snapshots=root/'snapshots'
   for p in (mods,disabled,state):p.mkdir()
   source=mods/'level.ucas';source.write_bytes(b'original-level');target=disabled/source.name
   with patch.object(tx,'LARGE_ASSET',1),patch.object(tx.shutil,'copy2',side_effect=AssertionError('A level payload was copied')):
    journal=tx.publish({target:source,source:None},state,(mods,disabled,state),lambda:True,running=lambda:False,snapshots=snapshots)
    record=json.loads(journal.read_text());row=next((i,row) for i,row in enumerate(record['files']) if row['before'])
    backup=tx.backup_path(journal,*row,snapshots)
    self.assertTrue(os.path.samefile(target,backup));self.assertFalse(source.exists())
    self.assertLess(sum(p.stat().st_size for p in (state/'backups').rglob('*') if p.is_file()),4096)
    record['status']='applying';tx.save(journal,record)
    tx.recover_pending(state,(mods,disabled,state),running=lambda:False,snapshots=snapshots)
    self.assertEqual(source.read_bytes(),b'original-level');self.assertFalse(target.exists())

 def test_no_hardlinks_blocks_before_any_level_is_changed(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);mods=root/'mods';disabled=root/'disabled';state=root/'state';snapshots=root/'snapshots'
   for p in (mods,disabled,state):p.mkdir()
   source=mods/'level.ucas';source.write_bytes(b'original-level');target=disabled/source.name
   with patch.object(tx,'LARGE_ASSET',1),patch.object(tx.os,'link',side_effect=OSError('No links')),patch.object(tx.shutil,'copy2',side_effect=AssertionError('Unexpected full copy')):
    with self.assertRaises(RuntimeError):tx.publish({target:source,source:None},state,(mods,disabled,state),lambda:True,running=lambda:False,snapshots=snapshots)
   self.assertEqual(source.read_bytes(),b'original-level');self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
