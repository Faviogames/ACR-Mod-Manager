from copy import deepcopy
import unittest

from wr_content import safe_asset, validate_references
from wr_content_sando import catalogue,validate_reviewed
from wr_content_reviewed import level_paths
from wr_menu_tables import _ownership,_row_map,merge_menu_tables


def ref(name,table,row):
    return dict(Name=name,StructType='DBReference',Value=[dict(Name='Table',Value=table),dict(Name='Row',Value=row)])


def table(rows):return dict(Imports=[],Exports=[dict(Table=dict(Data=rows))])


class ReviewedPathsTests(unittest.TestCase):
    def test_distinct_location_image_keys_follow_references(self):
        incoming={
            'DT_Tracks.uasset':table([dict(Name='Stage',Value=[ref('Location','TracksLocations','Country')])]),
            'DT_TracksLocations.uasset':table([dict(Name='Country',Value=[ref('Logo','TracksLocationsLogos','AuthorLogo'),ref('Background','TracksLocationsBackgrounds','AuthorBackdrop')])]),
            'DT_TracksLocationsLogos.uasset':table([dict(Name='AuthorLogo',Value=[])]),
            'DT_TracksLocationsBackgrounds.uasset':table([dict(Name='AuthorBackdrop',Value=[])])}
        baseline={name:table([]) for name in incoming}
        merged,_=merge_menu_tables(baseline,incoming,['Stage'])
        self.assertEqual(_ownership(incoming,'Stage')['DT_TracksLocationsLogos'],['AuthorLogo'])
        self.assertIn('AuthorBackdrop',_row_map(merged,'DT_TracksLocationsBackgrounds'))
        validate_references(merged)

    def test_custom_ui_is_limited_to_exact_reviewed_packages(self):
        self.assertEqual(safe_asset('acr/Content/AcrXs/Locations/Thierache/T_Thierache_Logo.uasset'),
                         'acr/Content/AcrXs/Locations/Thierache/T_Thierache_Logo.uasset')
        for path in ('acr/Content/AcrXs/Locations/Thierache/T_Other.uasset',
                     'acr/Content/AcrXs/Locations/Thierache/T_Thierache_Logo.exe',
                     'acr/Content/AcrXs/Locations/Thierache/../Bad.uasset'):
            with self.assertRaises(ValueError):safe_asset(path)

    def test_reviewed_level_path_and_changed_release_are_not_guessed(self):
        known=catalogue()['oxmod_thierache_s1']
        data=dict(known,id='oxmod_thierache_s1',producer='SandoRallyReviewed',track=known['tracks'][0])
        self.assertEqual(level_paths(data),['acr/Content/AcrXs/Stages/AcrXsThi04/AcrXsThi04.umap'])
        changed=deepcopy(data);changed['version']='3.4'
        with self.assertRaises(ValueError):validate_reviewed(changed)


if __name__=='__main__':unittest.main()
