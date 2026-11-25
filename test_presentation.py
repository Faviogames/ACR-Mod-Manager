from copy import deepcopy
from pathlib import Path
import tempfile,unittest,json
from types import SimpleNamespace
from unittest.mock import patch
from wr_content_presentation import preserve

def definition(description):
    return dict(producer='StageExporter',track='WrcgExample',tables={
        'TrackSelection/DT_TracksLocations.uasset':dict(Imports=[],Exports=[dict(Table=dict(Data=[dict(Name='WrcgCountry',Value=[
            dict(Name='HistoryAndTrivia',CultureInvariantString=description,Value=None),
            dict(Name='GameplayValue',Value=99)])]))])},assets={})

class PresentationTests(unittest.TestCase):
    def test_remembered_text_survives_reactivation_without_a_menu_row(self):
        old=definition('disabled owner text')
        old['presentation_overrides']=dict(fields={'TrackSelection/DT_TracksLocations.uasset':{'WrcgCountry':['HistoryAndTrivia']}},packages=[])
        new=definition('new bundled default');native=definition('irrelevant')['tables']
        native['TrackSelection/DT_TracksLocations.uasset']['Exports'][0]['Table']['Data']=[]
        with tempfile.TemporaryDirectory() as temp:preserve([dict(data=new,internal=True)],{'WrcgExample':old},native,Path(temp))
        value=new['tables']['TrackSelection/DT_TracksLocations.uasset']['Exports'][0]['Table']['Data'][0]['Value'][0]
        self.assertEqual(value['CultureInvariantString'],'disabled owner text')

    def test_previously_adopted_menu_text_is_not_replaced_by_bundled_defaults(self):
        old=definition('adopted owner text');old['catalog_origin']='official-local-adoption'
        new=definition('bundled default')
        with tempfile.TemporaryDirectory() as temp:preserve([dict(data=new,internal=True)],{'WrcgExample':old},old['tables'],Path(temp))
        value=new['tables']['TrackSelection/DT_TracksLocations.uasset']['Exports'][0]['Table']['Data'][0]['Value'][0]
        self.assertEqual(value['CultureInvariantString'],'adopted owner text')

    def test_changed_presentation_revision_invalidates_an_existing_cached_manifest(self):
        from wr_content_catalog import cached_record
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'catalog').mkdir();toc=root/'pakchunk99-WrcgExample_P.utoc'
            (root/'catalog'/(toc.stem+'.stage.json')).write_text('{}')
            (root/'official_presentation.json').write_text(json.dumps(dict(revisions={'WrcgExample':'new'})))
            data=dict(track='WrcgExample',producer='StageExporter',definition_revision='old',presentation_policy=2)
            manager=SimpleNamespace(state=root,load_manifest=lambda *a,**kw:data)
            with patch('wr_content_catalog.ROOT',root):
                self.assertFalse(cached_record(manager,root,toc,{}))
                data['definition_revision']='new';self.assertTrue(cached_record(manager,root,toc,{}))
                data['presentation_policy']=1;self.assertFalse(cached_record(manager,root,toc,{}))

    def test_known_legacy_placeholder_is_not_a_user_image_override(self):
        def image(key):return dict(Name='TrackImage',StructType='DBReference',Value=[dict(Name='Table',Value='TracksTextures'),dict(Name='Row',Value=key)])
        path='TrackSelection/DT_Tracks.uasset'
        old=dict(producer='StageExporter',track='WrcgExample',tables={path:dict(Imports=[],Exports=[dict(Table=dict(Data=[dict(Name='WrcgExample',Value=[image('HafrenSouthTrack')])]))])},assets={})
        old['presentation_overrides']=dict(fields={path:{'WrcgExample':['TrackImage']}},packages=[])
        new=deepcopy(old);new.pop('presentation_overrides')
        new['tables'][path]['Exports'][0]['Table']['Data'][0]['Value'][0]=image('WrcgExample_Background')
        with tempfile.TemporaryDirectory() as temp:preserve([dict(data=new,internal=True)],{'WrcgExample':old},old['tables'],Path(temp))
        value=new['tables'][path]['Exports'][0]['Table']['Data'][0]['Value'][0]
        self.assertEqual(value['Value'][1]['Value'],'WrcgExample_Background')
        self.assertNotIn('TrackImage',new['presentation_overrides']['fields'][path]['WrcgExample'])

    def test_serialization_flags_do_not_count_as_a_user_edit(self):
        old=definition('same text');current=deepcopy(old);new=definition('fresh catalogue')
        field=current['tables']['TrackSelection/DT_TracksLocations.uasset']['Exports'][0]['Table']['Data'][0]['Value'][0]
        field['IsZero']=False;field['PropertyTagFlags']='None'
        row=dict(data=new,internal=True)
        with tempfile.TemporaryDirectory() as temp:preserve([row],{'WrcgExample':old},current['tables'],Path(temp))
        self.assertNotIn('_presentation_changed',row)

    def test_old_generic_description_is_not_a_user_override(self):
        old=definition('Stages imported from WRC Generations. Free Practice only.')
        path='TrackSelection/DT_TracksLocations.uasset'
        old['presentation_overrides']=dict(fields={path:{'WrcgCountry':['HistoryAndTrivia']}},packages=[])
        new=definition('Portuguese author text')
        with tempfile.TemporaryDirectory() as temp:preserve([dict(data=new,internal=True)],{'WrcgExample':old},old['tables'],Path(temp))
        self.assertEqual(new['tables'][path]['Exports'][0]['Table']['Data'][0]['Value'][0]['CultureInvariantString'],'Portuguese author text')

    def test_user_can_deliberately_clear_a_previous_description(self):
        old=definition('old catalogue');new=definition('fresh catalogue');current=definition('')
        with tempfile.TemporaryDirectory() as temp:preserve([dict(data=new,internal=True)],{'WrcgExample':old},current['tables'],Path(temp))
        value=new['tables']['TrackSelection/DT_TracksLocations.uasset']['Exports'][0]['Table']['Data'][0]['Value'][0]
        self.assertEqual(value['CultureInvariantString'],'')

    def test_unchanged_managed_text_gets_new_catalogue_text(self):
        old=definition('old catalogue');new=definition('fresh catalogue')
        row=dict(data=new,internal=True)
        with tempfile.TemporaryDirectory() as temp:preserve([row],{'WrcgExample':old},old['tables'],Path(temp))
        self.assertEqual(new['tables'],definition('fresh catalogue')['tables'])
        self.assertNotIn('_presentation_changed',row)

    def test_user_edited_text_is_retained_and_not_gameplay(self):
        old=definition('old catalogue');new=definition('fresh catalogue');current=definition('owner edited')
        current['tables']['TrackSelection/DT_TracksLocations.uasset']['Exports'][0]['Table']['Data'][0]['Value'][1]['Value']=123
        row=dict(data=new,internal=True)
        with tempfile.TemporaryDirectory() as temp:preserve([row],{'WrcgExample':old},current['tables'],Path(temp))
        values=new['tables']['TrackSelection/DT_TracksLocations.uasset']['Exports'][0]['Table']['Data'][0]['Value']
        self.assertEqual(values[0]['CultureInvariantString'],'owner edited');self.assertEqual(values[1]['Value'],99)
        self.assertTrue(row['_presentation_changed'])
        # A later catalogue update must retain the explicit override even though it now matches the saved manifest.
        later=definition('next catalogue');prior=deepcopy(new)
        with tempfile.TemporaryDirectory() as temp:preserve([dict(data=later,internal=True)],{'WrcgExample':prior},new['tables'],Path(temp))
        self.assertEqual(later['tables']['TrackSelection/DT_TracksLocations.uasset']['Exports'][0]['Table']['Data'][0]['Value'][0]['CultureInvariantString'],'owner edited')

if __name__=='__main__':unittest.main()
