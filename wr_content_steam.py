"""Read-only Steam/ACR discovery. No game launch, network or exporter dependency."""
import argparse
import json
import os
from pathlib import Path
import re

APP_ID = '3917090'
MAX_VDF = 4 * 1024 * 1024


def vdf(text):
    tokens = []
    for match in re.finditer(r'//[^\r\n]*|"((?:\\.|[^"\\])*)"|([{}])|([^\s{}"]+)', text):
        if match.group().startswith('//'):
            continue
        tokens.append(re.sub(r'\\(["\\])', r'\1', match[1]) if match[1] is not None else match[2] or match[3])
    position = 0
    def block(depth=0):
        nonlocal position
        if depth > 16:
            raise ValueError('Steam metadata nesting limit')
        result = {}
        while position < len(tokens):
            key = tokens[position]; position += 1
            if key == '}':
                if not depth: raise ValueError('Unexpected closing brace')
                return result
            if key == '{' or position == len(tokens): raise ValueError('Invalid Steam metadata')
            value = tokens[position]; position += 1
            if value == '}': raise ValueError('Missing value')
            result[key.casefold()] = block(depth + 1) if value == '{' else value
        if depth: raise ValueError('Unclosed Steam metadata')
        return result
    return block()


def read_vdf(path):
    path = Path(path)
    if path.stat().st_size > MAX_VDF:
        raise ValueError('Steam metadata too large')
    return vdf(path.read_text(encoding='utf-8-sig', errors='strict'))


def steam_roots():
    roots = []
    if os.name == 'nt':
        import winreg
        for hive, key, name in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath'),
                                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    value, _ = winreg.QueryValueEx(handle, name)
                    if isinstance(value, str): roots.append(Path(value))
            except OSError:
                pass
    for variable in ('ProgramFiles(x86)', 'ProgramFiles'):
        if os.environ.get(variable): roots.append(Path(os.environ[variable]) / 'Steam')
    return roots


def game_paks(game):
    game = Path(game).resolve()
    paks = game / 'acr/Content/Paks'
    if (game/'acr/Binaries/Win64/acr.exe').is_file() and all((paks/name).is_file() for name in ('global.utoc', 'global.ucas')):
        return paks
    return None


def discover(roots=None):
    installations, warnings, seen_libraries, seen_games = [], [], set(), set()
    for root in (steam_roots() if roots is None else roots):
        root = Path(root).resolve()
        libraries = [root]
        folders = root/'steamapps/libraryfolders.vdf'
        if folders.is_file():
            try:
                entries = read_vdf(folders).get('libraryfolders', {})
                if not isinstance(entries, dict): raise ValueError('Invalid library list')
                for key, value in entries.items():
                    if not key.isdigit(): continue
                    value = value.get('path') if isinstance(value, dict) else value
                    if isinstance(value, str) and Path(value).is_absolute(): libraries.append(Path(value))
                if len(libraries) > 64: raise ValueError('Too many Steam libraries')
            except (OSError, ValueError, UnicodeError) as error:
                warnings.append('Cannot read library list: '+str(folders))
        for library in libraries[:64]:
            library = library.resolve()
            key = str(library).casefold()
            if key in seen_libraries: continue
            seen_libraries.add(key)
            manifest = library/('steamapps/appmanifest_'+APP_ID+'.acf')
            if not manifest.is_file(): continue
            try:
                app = read_vdf(manifest).get('appstate', {})
                directory = app.get('installdir')
                if str(app.get('appid')) != APP_ID or not isinstance(directory, str): raise ValueError('Wrong app manifest')
                if directory in ('', '.', '..') or any(c in directory for c in '/\\:\0'): raise ValueError('Invalid game directory')
                game = (library/'steamapps/common'/directory).resolve()
                paks = game_paks(game)
                if paks is None: continue
                key = str(game).casefold()
                if key not in seen_games:
                    seen_games.add(key)
                    installations.append(dict(game_root=str(game), game_paks=str(paks), steam_root=str(root),
                                              library_root=str(library), build_id=str(app.get('buildid', ''))))
            except (OSError, ValueError, UnicodeError, AttributeError):
                warnings.append('Cannot validate ACR manifest: '+str(manifest))
    return dict(installations=installations, warnings=warnings)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steam-root', type=Path)
    args = parser.parse_args()
    print(json.dumps(discover([args.steam_root] if args.steam_root else None), ensure_ascii=False))


if __name__ == '__main__': main()
