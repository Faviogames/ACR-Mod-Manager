"""UaTool import remapping without the frozen tools.acrmod.ugraph module."""
from copy import deepcopy


def remap_row(row, source, destination):
    result = deepcopy(row)
    memo = {}

    def remap(index, visiting):
        if index == 0:
            return 0
        if not isinstance(index, int) or isinstance(index, bool) or index > 0:
            raise ValueError('A menu import references a local export')
        if index in visiting or not 0 < -index <= len(source['Imports']):
            raise ValueError('Cyclic or invalid menu import')
        if index not in memo:
            incoming = deepcopy(source['Imports'][-index-1])
            incoming['OuterIndex'] = remap(incoming.get('OuterIndex', 0), visiting | {index})
            # Keep every serialized import field; equality ignores no class/package flags.
            imports = destination['Imports']
            if incoming not in imports:
                imports.append(incoming)
            memo[index] = -imports.index(incoming)-1
        return memo[index]

    def walk(value):
        if isinstance(value, dict):
            typ = value.get('$type', '')
            index = value.get('Value')
            if typ.split(',')[0].rsplit('.', 1)[-1] in ('ObjectPropertyData', 'ClassPropertyData', 'InterfacePropertyData'):
                if not isinstance(index, int) or isinstance(index, bool):
                    raise ValueError(f'Invalid object reference in menu row: {typ}: {index!r}')
                value['Value'] = remap(index, set())
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result)
    return result
