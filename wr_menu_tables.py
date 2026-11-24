"""Shared menu fusion, extracted from wr_mounts. No exporter/core imports."""
from copy import deepcopy
from pathlib import Path
from wr_content_imports import remap_row as _remap_row

def _rows(asset):
    return asset["Exports"][0]["Table"]["Data"]

def _field(row, name):
    return next((value for value in row.get("Value", ()) if value.get("Name") == name), None)

def _reference(value):
    if not value or value.get("StructType") != "DBReference":
        return None
    fields = {item["Name"]: item.get("Value") for item in value.get("Value", ())}
    return (fields["Table"], fields["Row"]) if fields.get("Table") and fields.get("Row") else None

def _references(value):
    if isinstance(value, dict):
        ref = _reference(value)
        if ref:
            yield ref
        for child in value.values():
            yield from _references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _references(child)

def _by_table(tables, name):
    return next((asset for relative, asset in tables.items() if Path(relative).stem == name), None)

def _row_map(tables, name):
    asset = _by_table(tables, name)
    return {row["Name"]: row for row in _rows(asset)} if asset else {}

def _ownership(tables, track):
    """Follow real references; SS1 must never claim the unrelated SS1R rows."""
    record = {"DT_Tracks": [track], "DT_TracksVariants": [], "DT_Levels": [], "DT_TracksTextures": [],
              "locations": []}
    row = _row_map(tables, "DT_Tracks").get(track)
    if row is not None:
        for table, name in _references(row):
            if not name or name == "None":
                continue
            if table == "TracksVariants":
                record["DT_TracksVariants"].append(name)
            elif table == "Levels" and (name == track or name.startswith(track + "_")):
                record["DT_Levels"].append(name)
            elif table == "TracksLocations":
                record["locations"].append(name)
    for name, variant in _row_map(tables, "DT_TracksVariants").items():
        if _reference(_field(variant, "Track")) == ("Tracks", track):
            record["DT_TracksVariants"].append(name)
    for table in ("DT_Levels", "DT_TracksTextures"):
        record[table].extend(name for name in _row_map(tables, table)
                             if name == track or name.startswith(track + "_"))
    for table in ("DT_TracksLocationsLogos", "DT_TracksLocationsBackgrounds"):
        record[table] = []
        for location in record['locations']:
            row = _row_map(tables, 'DT_TracksLocations').get(location)
            refs = [name for target,name in _references(row) if 'DT_'+target == table]
            record[table].extend(refs or ([location] if location in _row_map(tables,table) else []))
    return {key: sorted(set(values)) for key, values in record.items()}

def _join_ownership(*records):
    result = {}
    for record in records:
        for table, rows in record.items():
            result.setdefault(table, set()).update(rows)
    return {table: sorted(rows) for table, rows in result.items()}

def merge_menu_tables(baseline, incoming, active_tracks, owned=None, *, claimed=()):
    """Merge managed registrations while preserving every unmanaged baseline row.

    The arguments map paths relative to MENU_DIR to UaTool JSON objects. This
    pure table operation also permits fixture tests without cooking any stage.
    """
    active = set(active_tracks)
    missing = active - set(_row_map(incoming, "DT_Tracks"))
    if missing:
        raise ValueError("The new menu is missing managed track registrations: " + ", ".join(sorted(missing)))
    previous = deepcopy(owned or {})
    for track in active | set(claimed) | set(previous):
        previous[track] = _join_ownership(previous.get(track, {}), _ownership(baseline, track))
    current = {track: _ownership(incoming, track) for track in active}
    all_owned = _join_ownership(*previous.values(), *current.values())
    current_rows = _join_ownership(*current.values())
    active_locations = set(current_rows.get("locations", ()))
    merged = {}
    for relative in dict.fromkeys([*baseline, *incoming]):
        old = baseline.get(relative)
        update = incoming.get(relative)
        table = Path(relative).stem
        # A previously absent table retains the native rows supplied by the
        # regular builder (e.g. its stock texture rows).
        asset = deepcopy(old if old is not None else update)
        if old is None:
            merged[relative] = asset
            continue
        selected = set(current_rows.get(table, ()))
        if table == "DT_TracksLocations":
            selected = active_locations
        candidates = {row["Name"]: row for row in _rows(update) if row["Name"] in selected} if update else {}
        dropped = set(all_owned.get(table, ()))
        rows = []
        for row in _rows(old):
            key = row["Name"]
            if key in candidates:
                replacement = _remap_row(candidates.pop(key), update, asset)
                if table == "DT_TracksLocations":
                    old_tracks = _field(row, "Tracks")
                    new_tracks = _field(replacement, "Tracks")
                    if old_tracks and new_tracks:
                        new_tracks["Value"] = deepcopy(old_tracks["Value"]) + new_tracks["Value"]
                    default = _field(row, "DefaultVariant")
                    if default and _field(replacement, "DefaultVariant"):
                        _field(replacement, "DefaultVariant").update(deepcopy(default))
                rows.append(replacement)
            elif key not in dropped:
                rows.append(deepcopy(row))
        rows.extend(_remap_row(row, update, asset) for row in candidates.values())
        asset["Exports"][0]["Table"]["Data"] = rows
        merged[relative] = asset

    tracks = _row_map(merged, "DT_Tracks")
    variants = _row_map(merged, "DT_TracksVariants")
    locations = _by_table(merged, "DT_TracksLocations")
    empty_locations = set()
    if locations:
        for row in _rows(locations):
            prop = _field(row, "Tracks")
            if not prop:
                continue
            kept, seen = [], set()
            for item in prop["Value"]:
                ref = _reference(item)
                if ref is None or ref[0] != "Tracks":
                    kept.append(item)
                    continue
                track = ref[1]
                if track in seen or track not in tracks:
                    continue
                if _reference(_field(tracks[track], "Location")) != ("TracksLocations", row["Name"]):
                    continue
                seen.add(track)
                item["Name"] = str(len(kept))
                kept.append(item)
            prop["Value"] = kept
            default = _field(row, "DefaultVariant")
            ref = _reference(default)
            variant = variants.get(ref[1]) if ref else None
            default_track = _reference(_field(variant, "Track")) if variant else None
            if default and ref and (not variant or not default_track or default_track[0] != "Tracks"
                                    or default_track[1] not in seen):
                ordered_tracks = [ref[1] for item in kept if (ref := _reference(item)) and ref[0] == "Tracks"]
                candidate = next((reference[1] for track in ordered_tracks for reference in _references(tracks[track])
                                  if reference[0] == "TracksVariants" and reference[1] in variants), None)
                if candidate and _field(default, "Row"):
                    _field(default, "Row")["Value"] = candidate
            if not kept and row["Name"] in set(all_owned.get("locations", ())):
                empty_locations.add(row["Name"])
        locations["Exports"][0]["Table"]["Data"] = [r for r in _rows(locations)
                                                         if r["Name"] not in empty_locations]
    for name in ("DT_TracksLocationsBackgrounds", "DT_TracksLocationsLogos"):
        asset = _by_table(merged, name)
        if asset:
            asset["Exports"][0]["Table"]["Data"] = [r for r in _rows(asset) if r["Name"] not in empty_locations]
    ownership = {track: _join_ownership(previous.get(track, {}), current.get(track, {}))
                 for track in set(previous) | active}
    return merged, ownership

_NAME_KEYS = ("Name", "StructType", "ArrayType", "InnerType", "EnumType", "PropertyTypeName")

def _add_names(asset, obj):
    names, nm = set(), asset["NameMap"]

    def walk(o):
        if isinstance(o, dict):
            for k in _NAME_KEYS:
                v = o.get(k)
                if isinstance(v, str) and v and " " not in v and not v.startswith("{"):
                    names.add(v)
            if "NamePropertyData" in str(o.get("$type", "")) and isinstance(o.get("Value"), str):
                names.add(o["Value"])
            if "FTopLevelAssetPath" in str(o.get("$type", "")):       # soft paths are names too (the default logo
                for k in ("PackageName", "AssetName"):                 # of a location carried into another's write)
                    if isinstance(o.get(k), str):
                        names.add(o[k])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    # UE5 packages: the export data may only use the first NamesReferencedFromExportDataCount names; appended after it
    # they made ACR stop at start-up ("DT_TracksLocationsLogos: Bad name index 36/35", owner 2026-11-09). A name the
    # carried rows need goes into that range (moved there if it is past it) and the count grows with it.
    count = asset.get("NamesReferencedFromExportDataCount")
    if not isinstance(count, int) or not 0 <= count <= len(nm):
        have = set(nm)
        nm.extend(sorted(n for n in names if n not in have))
        return
    for n in sorted(names):
        if n in nm[:count]:
            continue
        if n in nm:
            nm.remove(n)
        nm.insert(count, n)
        count += 1
    asset["NamesReferencedFromExportDataCount"] = count
