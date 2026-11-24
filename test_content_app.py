"""UI read model, preview validation and the local HTTP trust boundary."""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
import zlib

import test_content  # the new UI must also work without wr/tools
from wr_content import preview_bytes
from wr_content_app import Engine, Server, stage_details, unregistered_packages


def png(width=1, height=1):
    def chunk(kind, raw):
        return struct.pack('>I',len(raw))+kind+raw+struct.pack('>I',zlib.crc32(kind+raw))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\0\0\0\xff'))+chunk(b'IEND',b'')


class FakeEngine:
    def __init__(self):
        self.lock=threading.RLock();self.previews={'test':png()};self.calls=[]
    def state(self): return {'app':'ACR Pak Manager','busy':False}
    def start(self, action, body): self.calls.append((action,body))


class AppTests(unittest.TestCase):
    def test_unregistered_packages_are_visible_and_not_actionable(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            for stem in ('pakchunk99-WrcgEsSS1_P','pakchunk99-WrcgZZStageMenu_P','pakchunk99-WrcgEsSS4_P'):
                for extension in ('.pak','.utoc','.ucas'):
                    (folder/(stem+extension)).write_bytes(b'x')
            (folder/'pakchunk99-WrcgEsSS4_P.stage.json').write_text('{}')
            rows=unregistered_packages(folder,True)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['name'],'pakchunk99-WrcgEsSS1_P')
            self.assertEqual(rows[0]['size'],3)
            self.assertFalse(rows[0]['valid']);self.assertTrue(rows[0]['registration_required'])

    def test_language_defaults_to_english_and_persists_without_replacing_config(self):
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/'manager.json'
            config.write_text(json.dumps({'game_paks':'keep-this-path'}))
            engine=Engine(config)
            self.assertEqual(engine.state()['language'],'en')
            self.assertEqual(engine.set_language('es'),'es')
            self.assertEqual(Engine(config).state()['language'],'es')
            self.assertEqual(json.loads(config.read_text())['game_paks'],'keep-this-path')
            with self.assertRaises(ValueError):engine.set_language('fr')
            self.assertEqual(Engine(config).state()['language'],'es')

    def test_wrc_creator_is_community_without_changing_identity(self):
        data=dict(id='favio_ke_ss1',track='WrcgKeSS1',tables={},version='test',built_with='test',files={})
        details=stage_details(data)
        self.assertEqual(details['author'],'Comunidad')
        self.assertEqual(details['id'],'favio_ke_ss1')

    def test_preview_checksum_and_dimensions(self):
        raw=png()
        record=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode())
        self.assertEqual(preview_bytes({'preview':record}),raw)
        with self.assertRaises(ValueError): preview_bytes({'preview':dict(record,sha256='bad')})
        raw=png(9000,9000)
        with self.assertRaisesRegex(ValueError,'Dimensiones'):
            preview_bytes({'preview':dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode())})

    def test_original_title_description_and_artwork_metadata(self):
        path=Path(__file__).parent/'tests/real/recipient/Paks/~mods/pakchunk99-WrcgEsSS1_P.stage.json'
        if not path.exists(): self.skipTest('Local real fixture absent')
        details=stage_details(json.loads(path.read_text(encoding='utf-8')))
        self.assertEqual(details['name'],'Riudecanyes');self.assertEqual(details['country'],'España')
        self.assertIn('Costa Daurada',details['description']);self.assertTrue(details['has_preview'])

    def test_server_requires_host_token_and_same_origin(self):
        engine=FakeEngine();server=Server(engine)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(method,path,headers=None,body=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            connection.request(method,path,body=body,headers=headers or {})
            response=connection.getresponse();code=response.status;data=response.read();connection.close();return code,data
        try:
            self.assertEqual(request('GET','/api/state')[0],403)
            auth={'X-App-Token':server.token}
            self.assertEqual(request('GET','/api/state',auth)[0],200)
            self.assertEqual(request('GET','/api/state',dict(auth,Host='evil.example'))[0],403)
            self.assertEqual(request('GET','/api/preview?id=test',auth),(200,png()))
            self.assertEqual(request('GET','/../wr_content.py')[0],404)
            body=json.dumps({'action':'sync'})
            self.assertEqual(request('POST','/api/action',auth,body)[0],403)
            self.assertEqual(request('POST','/api/action',dict(auth,Origin='https://evil.example'),body)[0],403)
            self.assertEqual(request('POST','/api/action',dict(auth,Origin=server.origin),body)[0],202)
            self.assertEqual(len(engine.calls),1)
        finally: server.shutdown();server.server_close();thread.join()


if __name__=='__main__': unittest.main()
