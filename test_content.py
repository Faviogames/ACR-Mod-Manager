"""Small safety checks for the new boundary/remapper and journaled installer."""
import importlib.abc
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


class NoCore(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'wr' or fullname == 'tools' or fullname.startswith('tools.'):
            raise AssertionError('Forbidden exporter dependency: ' + fullname)


sys.meta_path.insert(0, NoCore())
import wr_content as content
import wr_content_transaction as tx
from wr_content_imports import remap_row
from wr_menu_tables import _add_names


class ContentTests(unittest.TestCase):
    def test_import_remap_and_soft_reference(self):
        source = {'Imports': [{'ObjectName': 'Texture', 'OuterIndex': -2},
                              {'ObjectName': '/Game/Custom', 'OuterIndex': 0}]}
        target = {'Imports': [{'ObjectName': 'Existing', 'OuterIndex': 0}]}
        row = {'Value': [{'Name': 'Image', '$type': 'U.ObjectPropertyData, U', 'Value': -1},
                         {'Name': 'Level', '$type': 'U.SoftObjectPropertyData, U',
                          'Value': {'AssetPath': '/Game/Level'}}]}
        result = remap_row(row, source, target)
        self.assertEqual(result['Value'][0]['Value'], -3)
        self.assertEqual(target['Imports'][2]['OuterIndex'], -2)
        self.assertEqual(remap_row(row, source, target), result)
        self.assertEqual(len(target['Imports']), 3)
        self.assertEqual(row['Value'][0]['Value'], -1)
        source['Imports'][1]['OuterIndex'] = -1
        with self.assertRaisesRegex(ValueError, 'Cyclic'):
            remap_row(row, source, target)
        with self.assertRaises(ValueError):
            remap_row({'$type': 'U.ObjectPropertyData, U', 'Value': 1}, source, target)

    def test_asset_paths(self):
        for path in ('../outside.uasset', 'C:/bad.uasset',
                     'acr/Content/Data/UITextures/../../evil.uasset',
                     'acr/Content/Levels/Bad.umap', 'acr/Content/Data/UITextures/Bad.exe'):
            with self.assertRaises(ValueError):
                content.safe_asset(path)
        self.assertEqual(content.safe_asset('acr/Content/Data/UITextures/T.uasset'),
                         'acr/Content/Data/UITextures/T.uasset')

    def test_name_reference_range(self):
        asset = {'NameMap': ['Old', 'Late'], 'NamesReferencedFromExportDataCount': 1}
        _add_names(asset, {'$type': 'U.NamePropertyData, U', 'Value': 'Late'})
        self.assertEqual(asset['NamesReferencedFromExportDataCount'], 2)
        _add_names(asset, {'Name': 'New'})
        self.assertEqual(asset['NameMap'][:3], ['Old', 'Late', 'New'])

    def test_hash_cache_reuses_hardlinks_and_invalidates_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            calls = []
            cache = content.Hashes(root, lambda *args: calls.append(args))
            one, two = root/'one', root/'two'
            one.write_bytes(b'abc')
            first = cache.file(one)
            tx.copy_asset(one, two)
            cache.file(two)
            self.assertEqual(len(calls), 2)
            one.write_bytes(b'abcd')
            self.assertNotEqual(first, cache.file(one))
            self.assertEqual(len(calls), 4)

    def test_transaction_failure_restores_every_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mods, state = root/'mods', root/'state'
            mods.mkdir(); state.mkdir()
            changes = {}
            for i in range(3):
                path = mods/str(i); path.write_bytes(b'old')
                source = root/('new'+str(i)); source.write_bytes(b'new')
                changes[path] = source
            count = 0
            def fail_second(src, dst):
                nonlocal count
                count += 1
                if count == 2:
                    raise OSError('injected failure')
                os.replace(src, dst)
            with self.assertRaisesRegex(OSError, 'injected'):
                tx.publish(changes, state, (mods, state), lambda: True,
                           running=lambda: False, replace=fail_second)
            self.assertTrue(all(p.read_bytes() == b'old' for p in changes))
            journals = list((state/'backups').glob('*/journal.json'))
            self.assertEqual(json.loads(journals[0].read_text())['status'], 'rolled_back')

    def test_success_backup_and_rollback_refuses_later_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); mods = root/'mods'; mods.mkdir()
            state = root/'state'; state.mkdir()
            path = mods/'one'; path.write_bytes(b'old')
            source = root/'new'; source.write_bytes(b'new')
            journal = tx.publish({path: source}, state, (mods, state), lambda: True, running=lambda: False)
            self.assertEqual(path.read_bytes(), b'new')
            # Replace directory entry, preserving immutable hardlink snapshots.
            later = root/'later'; later.write_bytes(b'later'); os.replace(later, path)
            with self.assertRaisesRegex(RuntimeError, 'posterior'):
                tx.rollback(journal, (mods, state), running=lambda: False)

    def test_game_and_concurrent_changes_block_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root/'old'; path.write_bytes(b'old')
            source = root/'new'; source.write_bytes(b'new')
            with self.assertRaisesRegex(RuntimeError, 'Cierra ACR'):
                tx.publish({path: source}, root/'state', (root,), lambda: True, running=lambda: True)
            with self.assertRaisesRegex(RuntimeError, 'contenido cambió'):
                tx.publish({path: source}, root/'state', (root,), lambda: False, running=lambda: False)
            self.assertEqual(path.read_bytes(), b'old')

    def test_move_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); mods = root/'mods'; disabled = root/'disabled'; state = root/'state'
            mods.mkdir(); disabled.mkdir(); state.mkdir()
            path = mods/'one'; path.write_bytes(b'pak')
            moved = disabled/'one'
            journal = tx.publish({moved: path, path: None}, state, (mods, disabled, state),
                                 lambda: True, running=lambda: False)
            self.assertFalse(path.exists()); self.assertEqual(moved.read_bytes(), b'pak')
            record = json.loads(journal.read_text()); record['status'] = 'applying'; tx.save(journal, record)
            tx.recover_pending(state, (mods, disabled, state), running=lambda: False)
            self.assertEqual(path.read_bytes(), b'pak'); self.assertFalse(moved.exists())


if __name__ == '__main__':
    unittest.main()
