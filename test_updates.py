import io,json,unittest,urllib.error
from unittest.mock import patch
from pathlib import Path
import wr_content_updates as updates

class UpdateTests(unittest.TestCase):
 def setUp(self):self.release={'version':'0.1.0','repository':'Faviogames/ACR-Mod-Manager'}
 def response(self,tag='v0.2.0',assets=True,**values):
  repo=self.release['repository'];name='ACR-Mod-Manager-Setup.exe'
  data=dict(tag_name=tag,html_url=f'https://github.com/{repo}/releases/tag/{tag}',assets=[dict(name=name,browser_download_url=f'https://github.com/{repo}/releases/download/{tag}/{name}')] if assets else [],**values)
  return lambda url:io.BytesIO(json.dumps(data).encode())
 def test_versions_compare_numerically(self):
  self.assertGreater(updates.version('v1.10.0'),updates.version('1.9.9'))
  with self.assertRaises(ValueError):updates.version('v1.0/other')
 def test_new_downloadable_release_is_available(self):
  self.assertEqual(updates.latest(self.release,self.response())['status'],'available')
 def test_same_version_is_current(self):
  self.assertEqual(updates.latest(self.release,self.response('v0.1.0'))['status'],'current')
 def test_release_without_installer_is_not_a_downloadable_update(self):
  self.assertEqual(updates.latest(self.release,self.response(assets=False))['status'],'preparing')
 def test_prerelease_is_not_advertised(self):
  self.assertEqual(updates.latest(self.release,self.response(prerelease=True))['status'],'unpublished')
 def test_missing_public_repo_or_release_is_not_reported_as_current(self):
  def missing(url):raise urllib.error.HTTPError(url,404,'missing',{},None)
  self.assertEqual(updates.latest(self.release,missing)['status'],'unpublished')
 def test_foreign_release_url_is_rejected(self):
  data={'tag_name':'v9.0.0','html_url':'https://example.com/download','assets':[]}
  with self.assertRaises(ValueError):updates.latest(self.release,lambda url:io.BytesIO(json.dumps(data).encode()))

if __name__=='__main__':unittest.main()
