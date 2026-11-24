import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import wr_content_cleanup as clean
import wr_content_steam as steam
import wr_content_transaction as tx


class SteamTests(unittest.TestCase):
    def installation(self, library, name='ACR prueba ñ'):
        game=library/'steamapps/common'/name
        (game/'acr/Content/Paks').mkdir(parents=True)
        (game/'acr/Binaries/Win64').mkdir(parents=True)
        for file in ('global.utoc','global.ucas'):(game/'acr/Content/Paks'/file).touch()
        (game/'acr/Binaries/Win64/acr.exe').touch()
        (library/'steamapps/appmanifest_3917090.acf').write_text('"AppState" { "appid" "3917090" "installdir" "'+name+'" "buildid" "26756580" }',encoding='utf-8')
        return game

    def test_secondary_library_and_unicode_are_discovered_without_game_folder_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);steam_root=root/'Steam';library=root/'Games elsewhere'
            (steam_root/'steamapps').mkdir(parents=True)
            game=self.installation(library)
            escaped=str(library).replace('\\','\\\\')
            (steam_root/'steamapps/libraryfolders.vdf').write_text('"libraryfolders" { "0" { "path" "'+escaped+'" "apps" { "3917090" "1" } } }')
            found=steam.discover([steam_root])['installations']
            self.assertEqual([row['game_root'] for row in found],[str(game.resolve())])

    def test_legacy_library_file_and_duplicate_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.installation(root)
            escaped=str(root).replace('\\','\\\\')
            (root/'steamapps/libraryfolders.vdf').write_text('"LibraryFolders" { // old layout\n "1" "'+escaped+'" }')
            self.assertEqual(len(steam.discover([root,root])['installations']),1)

    def test_missing_game_malformed_metadata_and_traversal_are_not_installations(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'steamapps').mkdir()
            (root/'steamapps/libraryfolders.vdf').write_text('"libraryfolders" {')
            result=steam.discover([root]);self.assertEqual(result['installations'],[]);self.assertTrue(result['warnings'])
            self.installation(root)
            (root/'steamapps/appmanifest_3917090.acf').write_text('"AppState" { "appid" "3917090" "installdir" "../escape" }')
            self.assertEqual(steam.discover([root])['installations'],[])


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.state=self.root/'state';self.mods=self.root/'Paks/~mods';self.disabled=self.root/'disabled'
        self.state.mkdir();self.mods.mkdir(parents=True)
        self.manager=SimpleNamespace(state=self.state,mods=self.mods,roots=(self.state,self.mods,self.disabled),config={})

    def tearDown(self):self.temp.cleanup()

    def backup(self,number,*,status='applied',pinned=False,snapshot=False,extra=False):
        folder=self.state/'backups'/format(number,'016x');(folder/'before').mkdir(parents=True)
        raw=b'old menu '+str(number).encode();(folder/'before/0').write_bytes(raw)
        rows=[dict(target=str(self.mods/'pakchunk99-WrcgTables_P.ucas'),before=hashlib.sha256(raw).hexdigest(),after='b'*64),
              dict(target=str(self.state/'installed.json'),before=None,after='c'*64)]
        if snapshot:rows[0]['volume_snapshot']=True
        tx.save(folder/'journal.json',dict(status=status,files=rows,pinned=pinned))
        os.utime(folder/'journal.json',(1000+number,1000+number))
        if extra:(folder/'my-notes.txt').write_text('keep me')
        return folder

    def test_newest_three_are_kept_and_older_menu_backups_are_cleaned(self):
        folders=[self.backup(i) for i in range(1,7)]
        preview=clean.cleanup_locked(self.manager,dry_run=True,running=lambda:False)
        self.assertEqual(len(preview['planned']),3);self.assertTrue(all(p.exists() for p in folders))
        result=clean.cleanup_locked(self.manager,running=lambda:False)
        self.assertEqual(result['removed_backups'],3)
        self.assertEqual([p.exists() for p in folders],[False,False,False,True,True,True])

    def test_pinned_level_snapshots_and_budget_excess_remain_protected(self):
        pinned=self.backup(1,pinned=True);level=self.backup(2,snapshot=True)
        for i in range(3,8):self.backup(i)
        clean.cleanup_locked(self.manager,running=lambda:False)
        self.assertTrue(pinned.exists());self.assertTrue(level.exists())

    def test_recovery_or_unknown_files_block_cleanup(self):
        old=self.backup(1);self.backup(2,status='applying')
        for i in range(3,8):self.backup(i)
        result=clean.cleanup_locked(self.manager,running=lambda:False)
        self.assertIn('deferred',result);self.assertTrue(old.exists())

    def test_corrupt_backup_and_unrecognized_user_data_are_not_deleted(self):
        old=self.backup(1);(old/'before/0').write_bytes(b'corrupted')
        for i in range(2,6):self.backup(i)
        result=clean.cleanup_locked(self.manager,running=lambda:False)
        self.assertTrue(old.exists());self.assertTrue(result['warnings'])
        unknown=self.backup(10,extra=True)
        result=clean.cleanup_locked(self.manager,running=lambda:False)
        self.assertIn('deferred',result);self.assertTrue((unknown/'my-notes.txt').exists())

    def test_corrupt_newest_copies_cannot_displace_older_usable_recovery(self):
        folders=[self.backup(i) for i in range(1,7)]
        for folder in folders[-3:]:
            (folder/'before/0').write_bytes(b'corrupt recent copy')
        result=clean.cleanup_locked(self.manager,running=lambda:False)
        self.assertIn('deferred',result)
        self.assertEqual(result['removed_backups'],0)
        self.assertTrue(all(folder.exists() for folder in folders))

    def test_game_open_disables_cleanup_and_no_changes_creates_no_new_backup(self):
        for i in range(1,7):self.backup(i)
        result=clean.cleanup_locked(self.manager,running=lambda:True)
        self.assertEqual(result['removed_backups'],0)
        self.assertEqual(len(list((self.state/'backups').iterdir())),6)

    def test_only_marked_dead_old_temporaries_are_removed(self):
        old=self.state/'build-abcdefgh';old.mkdir();(old/'data.txt').write_text('temporary')
        tx.save(old/'.acr-manager-temp.json',dict(schema='acr-manager-temp/1',pid=999999999,directory=str(old.resolve())))
        for item in [old,*old.iterdir()]:os.utime(item,(1,1))
        unknown=self.state/'build-ijklmnop';unknown.mkdir();(unknown/'user.txt').write_text('not ours')
        with patch.object(tx,'pid_alive',return_value=False):
            result=clean.cleanup_locked(self.manager,running=lambda:False,now=time.time())
        self.assertEqual(result['removed_temporaries'],1);self.assertFalse(old.exists());self.assertTrue(unknown.exists())

    def test_live_marked_temporary_and_native_source_are_protected(self):
        native=self.root/'native-cache';native.mkdir()
        source=self.root/'game.ucas';source.write_bytes(b'original game content')
        orphan=native/'catalog-abcdefgh';orphan.mkdir()
        os.link(source,orphan/'global.ucas')
        tx.save(orphan/'.acr-manager-temp.json',dict(schema='acr-manager-temp/1',pid=999999999,directory=str(orphan.resolve())))
        for item in [orphan,*orphan.iterdir()]:os.utime(item,(1,1))
        self.manager.config['native_cache']=str(native)
        with patch.object(tx,'pid_alive',return_value=True):
            self.assertEqual(clean.cleanup_locked(self.manager,running=lambda:False)['removed_temporaries'],0)
        with patch.object(tx,'pid_alive',return_value=False):
            self.assertEqual(clean.cleanup_locked(self.manager,running=lambda:False)['removed_temporaries'],1)
        self.assertEqual(source.read_bytes(),b'original game content')

    def test_invalid_policy_cannot_trigger_unexpected_cleanup(self):
        old=self.backup(1)
        self.manager.config['cleanup']={'enabled':'false'}
        with self.assertRaises(ValueError):clean.cleanup_locked(self.manager,running=lambda:False)
        self.assertTrue(old.exists())

    def test_cleanup_keeps_a_valid_rollback(self):
        for i in range(1,7):self.backup(i)
        clean.cleanup_locked(self.manager,running=lambda:False)
        latest=self.state/'backups'/format(6,'016x')
        menu=self.mods/'pakchunk99-WrcgTables_P.ucas';menu.write_bytes(b'new')
        journal=json.loads((latest/'journal.json').read_text())
        journal['files'][0]['after']=tx.sha(menu)
        journal['files'][1]['after']=None
        tx.save(latest/'journal.json',journal)
        tx.rollback(latest/'journal.json',self.manager.roots,running=lambda:False)
        self.assertEqual(menu.read_bytes(),b'old menu 6')


if __name__=='__main__':unittest.main()
