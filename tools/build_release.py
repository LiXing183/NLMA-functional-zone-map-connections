"""Validate and build a deterministic QGIS installation ZIP, without network I/O."""
import ast
import configparser
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'nluz_background'
FILES = (
    '__init__.py', 'core.py', 'engine.py', 'plugin.py', 'storage.py',
    'metadata.txt', 'icon.svg', 'counties.json', 'county_order.json',
    'announcements.json', 'LICENSE', 'README.md', 'CHANGELOG.md', '使用說明.txt',
)


def main():
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(SOURCE / 'metadata.txt', encoding='utf-8-sig')
    general = metadata['general']
    required = ('name', 'description', 'about', 'version', 'qgisMinimumVersion',
                'qgisMaximumVersion', 'author', 'email', 'homepage', 'repository',
                'tracker', 'icon', 'changelog')
    for field in required:
        if not general.get(field, '').strip():
            raise ValueError('Missing metadata field: ' + field)
    version = general['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Expected a three-part release version')
    if general['icon'] != 'icon.svg' or general.getboolean('experimental'):
        raise ValueError('Unexpected icon or release status')
    for field in ('homepage', 'repository', 'tracker'):
        if not general[field].startswith('https://github.com/LiXing183/NLMA-functional-zone-map-connections'):
            raise ValueError('Unexpected project URL: ' + field)
    hashes = {}
    for name in FILES:
        file = SOURCE / name
        data = file.read_bytes()
        text = data.decode('utf-8-sig')
        if not text.strip():
            raise ValueError('Empty file: ' + name)
        if file.suffix == '.py':
            compile(text, name, 'exec')
        if file.suffix == '.json':
            json.loads(text)
        hashes[name] = hashlib.sha256(data).hexdigest()
    entry = ast.parse((SOURCE / '__init__.py').read_text(encoding='utf-8'))
    if not any(isinstance(n, ast.FunctionDef) and n.name == 'classFactory' for n in entry.body):
        raise ValueError('Missing classFactory')
    ElementTree.fromstring((SOURCE / 'icon.svg').read_text(encoding='utf-8'))
    counties = json.loads((SOURCE / 'counties.json').read_text(encoding='utf-8'))
    order = json.loads((SOURCE / 'county_order.json').read_text(encoding='utf-8'))
    if len(counties) != 44 or len(order) != 22 or len(set(order)) != 22:
        raise ValueError('Unexpected county catalog size')
    if {(r['county'], r['version']) for r in counties} != {
            (county, stage) for county in order for stage in ('報部版', '公展版')}:
        raise ValueError('County/stage catalog is incomplete')
    for file in (ROOT / 'README.md', ROOT / 'CHANGELOG.md', ROOT / 'docs/VALIDATION.md',
                 SOURCE / 'README.md'):
        for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
            if '://' not in target and not (file.parent / target.split('#')[0]).is_file():
                raise ValueError('Missing documentation target: ' + target)
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    package = destination / ('NLMA-functional-zone-map-connections-' + version + '.zip')
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(FILES):
            info = zipfile.ZipInfo('nluz_background/' + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (SOURCE / name).read_bytes())
    with zipfile.ZipFile(package) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(FILES):
            raise ValueError('ZIP integrity failure')
        for name in FILES:
            if archive.read('nluz_background/' + name) != (SOURCE / name).read_bytes():
                raise ValueError('Archive/source mismatch: ' + name)
    if package.stat().st_size >= 25 * 1024 * 1024:
        raise ValueError('Package exceeds QGIS size limit')
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    package.with_suffix('.zip.sha256').write_text(digest + '  ' + package.name + '\n', encoding='ascii')
    manifest = {'version': version, 'package': package.name, 'sha256': digest,
                'bytes': package.stat().st_size, 'files': hashes,
                'local_structure_check': 'passed', 'remote_links_verified': False,
                'qgis_repository_uploaded': False}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print('PASS: metadata, syntax, catalogs, documentation, icon and archive/source equality')
    print('Package:', package.name, '(' + str(package.stat().st_size) + ' bytes)')
    print('SHA256:', digest)


if __name__ == '__main__':
    main()
