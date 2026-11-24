import hashlib
import http.client
from pathlib import Path
import struct
import threading
import unittest

from test_content_app import FakeEngine
from wr_content_app import Server

ROOT=Path(__file__).resolve().parent


class BrandAssetsTests(unittest.TestCase):
    def test_icon_has_all_windows_sizes_and_original_logo_is_preserved(self):
        raw=(ROOT/'ui/assets/app.ico').read_bytes()
        self.assertEqual(struct.unpack_from('<HH',raw),(0,1))
        count=struct.unpack_from('<H',raw,4)[0]
        sizes=[]
        for i in range(count):
            width,height,_,_,planes,bits,size,offset=struct.unpack_from('<BBBBHHII',raw,6+i*16)
            sizes.append(width or 256)
            self.assertEqual((width,height,planes,bits),(width,width,1,32))
            self.assertTrue(raw[offset:offset+size].startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(sizes,[16,24,32,48,64,128,256])
        self.assertEqual(hashlib.sha256((ROOT/'ui/assets/acr-logo.jpg').read_bytes()).hexdigest(),
                         '2bd0f3e217c9b64c692cd2382aad27525054c2ea6126b6b8859a9b595e1de042')

    def test_new_header_and_icon_are_served_but_arbitrary_asset_paths_are_not(self):
        server=Server(FakeEngine());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def get(path):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            connection.request('GET',path);r=connection.getresponse();result=(r.status,r.read());connection.close();return result
        try:
            status,html=get('/');self.assertEqual(status,200);self.assertIn(b'ACR Pak Manager',html);self.assertIn(b'brand-logo',html)
            for name in ('acr-logo.jpg','app.ico','app-icon.svg'):
                self.assertEqual(get('/assets/'+name),(200,(ROOT/'ui/assets'/name).read_bytes()))
            self.assertEqual(get('/assets/../../app_release.json')[0],404)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
