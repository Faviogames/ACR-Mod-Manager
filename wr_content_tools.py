"""Only subprocesses and standard Python; never imports the frozen exporter."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from wr_content_transaction import sha
from wr_menu_tables import _add_names

MAIN = 'acr/Content/Data/Database/Main/'
TABLES = {MAIN + 'Common/DT_Levels.uasset'} | {
    MAIN + 'TrackSelection/' + name + '.uasset' for name in (
        'DT_Tracks', 'DT_TracksLocations', 'DT_TracksVariants', 'DT_TracksTextures',
        'DT_TracksLocationsLogos', 'DT_TracksLocationsBackgrounds')}
PENALTY = 'acr/Content/Data/Gameplay/DA_RacePenaltyDataFreePractice.uasset'
ASSET_EXTS = {'.uasset', '.uexp', '.ubulk', '.uptnl'}


def run(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True,
                            encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError((result.stdout + '\n' + result.stderr)[-6000:])
    return result.stdout


def asset_path(value):
    value = value.replace('\\', '/')
    while value.startswith('../'):
        value = value[3:]
    path = Path(value)
    if path.is_absolute() or path.drive or '..' in path.parts or not value.startswith('acr/Content/'):
        raise ValueError('Ruta de asset inválida: ' + value)
    return path.as_posix()


class Tools:
    def __init__(self, config, log=print):
        self.config = config
        self.log = log
        self.ret = Path(config['retoc'])
        self.ua = Path(config['uatool'])
        self.mapping = Path(config['mapping'])
        self.stock = Path(config['game_paks'])

    def listing(self, toc):
        result = {}
        for line in run(self.ret, 'list', toc, '--path').splitlines():
            columns = line.split(maxsplit=3)
            if len(columns) == 4 and columns[2] == 'ExportBundleData':
                if '/acr/Content/' not in columns[3].replace('\\', '/'):
                    continue
                relative = asset_path(columns[3])
                result[relative] = columns[1]
        return result

    def dump(self, asset, scratch):
        output = Path(scratch) / (hashlib.sha256(str(asset).encode()).hexdigest() + '.json')
        run(self.ua, 'dumpjson', asset, self.mapping, output)
        data = json.loads(output.read_text(encoding='utf-8-sig'))
        if any(i.get('ObjectName') == 'UnknownExport' or '/Engine/UnknownPackage' in str(i)
               for i in data.get('Imports', [])):
            raise ValueError('Importaciones sin resolver: ' + str(asset))
        return data

    def write(self, data, output, scratch):
        _add_names(data, data)
        _add_names(data, [{'Name': imp[key]} for imp in data.get('Imports', [])
                          for key in ('ObjectName', 'ClassName', 'ClassPackage', 'PackageName')
                          if isinstance(imp.get(key), str)])
        temporary = Path(scratch) / 'write.json'
        temporary.write_text(json.dumps(data), encoding='utf-8')
        output.parent.mkdir(parents=True, exist_ok=True)
        run(self.ua, 'fromjson', temporary, self.mapping, output)
        # Reject RawExport or schema losses immediately, before any installation.
        back = self.dump(output, scratch)
        if data.get('Exports') != back.get('Exports'):
            # UaTool recomputes sizes/offsets; compare serialized property content below.
            def contents(j):
                return [(e.get('ObjectName'), e.get('Data'), e.get('Table')) for e in j['Exports']]
            if contents(data) != contents(back):
                def difference(a, b, path=''):
                    if isinstance(a, dict) and isinstance(b, dict):
                        for key in a.keys() | b.keys():
                            if a.get(key) != b.get(key):
                                return difference(a.get(key), b.get(key), path+'/'+str(key))
                    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
                        for i, (x, y) in enumerate(zip(a, b)):
                            if x != y:
                                return difference(x, y, path+'/'+str(i))
                    return f'{path}: {str(a)[:180]} -> {str(b)[:180]}'
                raise ValueError('UaTool cambió los datos al serializar ' + str(output) + ': ' + difference(contents(data), contents(back)))

    @contextmanager
    def stock_view(self, scratch):
        """Fresh native inputs only. An explicit test view is rechecked against the real game."""
        catalogs = sorted(p for p in self.stock.glob('*.utoc') if
                          p.name.lower() == 'global.utoc' or
                          re.fullmatch(r'pakchunk\d+(?:optional)?-Windows\.utoc', p.name, re.I))
        if not any(p.name.lower() == 'global.utoc' for p in catalogs):
            raise ValueError('No se encuentra el catálogo original de ACR')
        # Tests on another drive may copy the two original containers that own tables.
        # Production uses the existing same-volume hardlink approach, never old baselines.
        if self.config.get('test_stock_view'):
            view = Path(self.config['test_stock_view'])
            for toc in view.glob('*.utoc'):
                if toc.name not in {p.name for p in catalogs} or sha(toc) != sha(self.stock/toc.name):
                    raise ValueError('La vista de prueba no corresponde al juego actual')
                for ext in ('.ucas',):
                    copy = toc.with_suffix(ext)
                    original = (self.stock/toc.name).with_suffix(ext)
                    if not copy.is_file() or sha(copy) != sha(original):
                        raise ValueError('Datos originales de prueba distintos: ' + str(copy))
            yield view
            return
        # This folder belongs to this operation and is outside the game's Paks.
        parent = Path(self.config.get('native_cache', self.stock.parents[2]/'StageContentNative'))
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent, prefix='catalog-') as temp:
            view = Path(temp)
            for toc in catalogs:
                for ext in ('.utoc', '.ucas'):
                    source = toc.with_suffix(ext)
                    if source.exists():
                        try:
                            os.link(source, view/source.name)
                        except OSError as exc:
                            raise RuntimeError('native_cache debe estar en el disco del juego y permitir enlaces duros') from exc
            yield view

    def extract_stock(self, destination, scratch):
        self.log('Leyendo tablas originales del juego actual…')
        with self.stock_view(scratch) as view:
            for selected in ('Data/Database/Main/Common/DT_Levels',
                             'Data/Database/Main/TrackSelection/DT_',
                             'DA_RacePenaltyDataFreePractice'):
                run(self.ret, 'to-legacy', view, destination, '-f', selected,
                    '--version', 'UE5_6', '--no-shaders')
        tables = {}
        for relative in sorted(TABLES):
            path = destination/relative
            if path.exists():
                tables[relative[len(MAIN):]] = self.dump(path, scratch)
        required = TABLES - {MAIN + 'TrackSelection/DT_TracksTextures.uasset'}
        if not required <= {MAIN+p for p in tables}:
            raise ValueError('Extracción original incompleta: ' + str(required-{MAIN+p for p in tables}))
        penalties = list(destination.rglob('DA_RacePenaltyDataFreePractice.uasset'))
        if len(penalties) != 1:
            raise ValueError('Tabla original de penalizaciones ausente o ambigua')
        return tables, penalties[0]

    def pack(self, legacy, output, name):
        from wr_iostore_compress import compress_build
        self.log('Empaquetando y verificando tablas…')
        output.mkdir(parents=True, exist_ok=True)
        toc = output/(name+'.utoc')
        run(self.ret, 'to-zen', legacy, toc, '--version', 'UE5_6')
        compress_build(toc, log=self.log)
        run(self.ret, 'verify', toc)
        expected = {p.relative_to(legacy).as_posix() for p in legacy.rglob('*.uasset')}
        actual = set(self.listing(toc))
        if actual != expected:
            raise ValueError('El contenido del pak de tablas no coincide con lo preparado')
        return toc
