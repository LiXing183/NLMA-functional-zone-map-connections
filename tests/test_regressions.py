"""Offline regressions using production method bodies and fault injection.
No QGIS runtime or network access; real files and minidom model serialization.
"""
import ast
import importlib.util
import json
import math
import struct
import tempfile
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType, SimpleNamespace as NS
from unittest.mock import patch
from xml.dom import minidom

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'nluz_background'
WORK = ROOT / '.test-work'
WORK.mkdir(exist_ok=True)
passed = []


def load(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core, storage = load('core'), load('storage')
for path in SOURCE.glob('*.py'):
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')


def methods(file, cls, scope):
    tree = ast.parse((SOURCE / file).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    exec(compile(ast.Module(body=[n for n in node.body if isinstance(n, ast.FunctionDef)],
                            type_ignores=[]), file, 'exec'), scope)
    return scope


def bind(obj, scope, names):
    for name in names:
        setattr(obj, name, MethodType(scope[name], obj))
    return obj


class Signal:
    def __init__(self): self.callbacks = []
    def connect(self, callback): self.callbacks.append(callback)
    def disconnect(self, callback): self.callbacks.remove(callback)
    def emit(self, *args):
        for cb in list(self.callbacks): cb(*args)


class Timer:
    def __init__(self, *args): self.timeout, self.started = Signal(), False
    def setSingleShot(self, value): pass
    def start(self, *args): self.started = True
    def stop(self): self.started = False
    def deleteLater(self): self.deleted = True


class Request:
    Attribute = NS(HttpStatusCodeAttribute=1, CacheLoadControlAttribute=2)
    CacheLoadControl = NS(AlwaysNetwork=3)
    def __init__(self, url): self.url = url
    def setRawHeader(self, *args): pass
    def setAttribute(self, *args): pass


class Reply:
    def __init__(self, payload=b'png', status=200, error=0):
        self.finished = Signal()
        self.payload, self.status, self.network_error = payload, status, error
        self.deleted, self.aborted = False, False
    def attribute(self, key): return self.status
    def error(self): return self.network_error
    def readAll(self): return self.payload
    def deleteLater(self): self.deleted = True
    def abort(self): self.aborted = True; self.finished.emit()


class Node:
    def __init__(self, node): self.node = node
    def firstChildElement(self, tag):
        return Node(next((n for n in self.node.childNodes if n.nodeType == n.ELEMENT_NODE
                          and n.tagName == tag), None))
    def firstChild(self): return Node(self.node.firstChild)
    def isNull(self): return self.node is None
    def appendChild(self, child): self.node.appendChild(child.node)
    def replaceChild(self, new, old): self.node.replaceChild(new.node, old.node)


class Document:
    def __init__(self): self.doc = minidom.parseString('<qgis/>')
    def createElement(self, tag): return Node(self.doc.createElement(tag))
    def createTextNode(self, value): return Node(self.doc.createTextNode(value))
    def layer_element(self, layer):
        element = self.createElement('maplayer')
        for tag, value in [('id', layer.id()), ('datasource', layer.source())]:
            child = self.createElement(tag)
            child.appendChild(self.createTextNode(value))
            element.appendChild(child)
        return element  # QGIS writeMapLayer occurs before this is appended.
    def append(self, node): self.doc.documentElement.appendChild(node.node)
    def source(self): return Path(self.doc.getElementsByTagName('datasource')[0].firstChild.data)


def png(width, height, color=1):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    raw = (b'\0' + bytes((color, 120, 180, 255)) * width) * height
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


class Image:
    def __init__(self, data): self.size = storage.png_size(data)
    def isNull(self): return False
    def width(self): return self.size[0]
    def height(self): return self.size[1]
    def save(self, *args): raise AssertionError('PNG must not be recompressed')


class Renderer:
    def __init__(self, opacity=0.42): self.value = opacity
    def opacity(self): return self.value
    def setOpacity(self, value): self.value = value
    def clone(self): return Renderer(self.value)


class Layer:
    def __init__(self, source):
        self.path, self.crs_value, self.title = str(source), 'EPSG:3826', core.LAYER_NAME
        self.render = Renderer()
        self.props = {core.PROPERTY + k: v for k, v in {
            'enabled': '1', 'county': '臺北市', 'version': '報部版', 'status': 'connected',
            'image_state': 'ready', 'image_county': '臺北市', 'image_version': '報部版',
            'image_crs': 'EPSG:3826', 'updates': 0}.items()}
        self.failures = set()
    def fault(self, name):
        if name in self.failures:
            self.failures.remove(name)
            raise RuntimeError('Injected ' + name)
    def source(self): return self.path
    def id(self): return 'L1'
    def name(self): return self.title
    def setName(self, name): self.title = name
    def setDataSource(self, source, *args):
        self.path, self.crs_value, self.render = str(source), '', Renderer(1)
        self.fault('source')
    def isValid(self): return Path(self.path).is_file()
    def crs(self): return NS(authid=lambda: self.crs_value, value=self.crs_value)
    def setCrs(self, crs):
        self.fault('crs')
        self.crs_value = getattr(crs, 'value', crs)
    def renderer(self): return self.render
    def setRenderer(self, renderer): self.render = renderer
    def setCustomProperty(self, key, value):
        if key == core.PROPERTY + 'image_county': self.fault('property')
        self.props[key] = value
    def customProperty(self, key, default=''): return self.props.get(key, default)
    def removeCustomProperty(self, key): self.props.pop(key, None)
    def triggerRepaint(self): self.fault('repaint')
    def isInScaleRange(self, scale): return True


class CRS:
    def __init__(self, value): self.value = getattr(value, 'value', value)
    def __eq__(self, other): return self.value == getattr(other, 'value', other)


class Style:
    def readFromLayer(self, layer): self.opacity = layer.renderer().opacity()
    def isValid(self): return True
    def writeToLayer(self, layer):
        layer.fault('style')
        layer.renderer().setOpacity(self.opacity)


es = methods('engine.py', 'Engine', {
    **{key: getattr(core, key) for key in ('PROPERTY', 'IMAGE_PROPERTIES', 'displayed_image',
        'version_label', 'response_error', 'token_due', 'SERVICE', 'PROXY')},
    'QTimer': Timer, 'QUrl': str, 'QNetworkRequest': Request, 'QImage': NS(fromData=Image),
    'png_size': storage.png_size, 'uuid': uuid, 'datetime': datetime, 'timezone': timezone,
    'json': json, 'Path': Path, 'QgsMapLayerStyle': Style,
    'QgsCoordinateReferenceSystem': CRS,
    'QgsRasterLayer': lambda source, *args: NS(isValid=lambda: Path(source).is_file()),
    'time': NS(monotonic=lambda: 1800),
    'urlencode': __import__('urllib.parse', fromlist=['urlencode']).urlencode,
})
ps = methods('plugin.py', 'Plugin', {
    **{key: getattr(core, key) for key in ('TITLE', 'PROPERTY', 'LAYER_NAME', 'displayed_image', 'version_label')},
    'Path': Path, 'snapshot': storage.snapshot, 'QgsRasterLayer': Layer,
})

assert core.token_due(0, 1800) and not core.token_due(0, 1799.99)
for county in ['金門縣', '澎湖縣', '連江縣']: assert core.county_epsg(county) == 3825
assert core.county_epsg('臺北市') == 3826
for code in (401, 403, 498, 499):
    assert core.response_error(200, json.dumps({'error': {'code': code}}).encode())
    assert core.response_error(code, b'')
assert 'TLS' in core.response_error(None, b'', 6)
assert 'DNS' in core.response_error(None, b'', 3)
assert '代理' in core.response_error(407, b'', 105)
assert 'Token' in core.response_error(200, b'{"error":{"code":498}}', 203)
assert core.response_error(200, b'<html/>', 0, allow_html=True) is None
assert core.response_error(200, b'<html/>') and core.response_error(200, b'E1')
assert core.response_error(200, png(2, 2)) is None
page = ('const layerToken = "' + 'a'*32 + '"; const m_lyrcode = ' +
        json.dumps([{'name':'臺北市','version':'報部版','id':21}]) + ';').encode()
assert core.parse_entry(page, '臺北市', '報部版') == ('a'*32, 21)
try:
    core.parse_entry(page, '臺北市', '公展版')
    raise AssertionError('Wrong version accepted')
except ValueError:
    pass
ann = json.loads((SOURCE / 'announcements.json').read_text(encoding='utf-8'))
assert '113年8月15日' in core.announcement_text(ann, '臺北市', '報部版')
assert '110年12月31日' in core.announcement_text(ann, '臺北市', '公展版')
passed.append('syntax, defaults, CRS, 30-minute boundary, auth and transport errors, announcements')

for bounds in [(300000, 2700000, 302600, 2701700), (10, 20, 110, 320),
               (10, 20, 10.001, 120), (177777, 2222222, 183456.7, 2229777.8)]:
    bbox, size, res = core.render_geometry(bounds, 4096)
    assert max(size) <= 4096 and min(size) >= 1
    assert math.isclose((bbox[2]-bbox[0])/size[0], res, rel_tol=1e-8)
    assert math.isclose((bbox[3]-bbox[1])/size[1], res, rel_tol=1e-8)
    assert bbox[0] <= bounds[0] + 1e-9 and bbox[1] <= bounds[1] + 1e-9
    assert bbox[2] >= bounds[2] - 1e-9 and bbox[3] >= bounds[3] - 1e-9
passed.append('rectangular aspect ratio and pixel-center georeferencing')

for stale in ('current', 'project', 'view', 'unload'):
    reply = Reply()
    received, errors = [], []
    e = NS(epoch=0, image_epoch=0, closed=False, entry='https://example.test/',
           net=NS(get=lambda req: reply), fail=errors.append)
    es['get'](e, 'https://example.test/', received.append, 'image')
    if stale == 'project': e.epoch += 1
    if stale == 'view': e.image_epoch += 1
    if stale == 'unload': e.closed = True
    reply.finished.emit()
    assert bool(received) == (stale == 'current') and not errors and reply.deleted
reply = Reply(b'{"error":{"code":498}}')
received, errors = [], []
e = NS(epoch=0, image_epoch=0, closed=False, entry='https://example.test/',
       net=NS(get=lambda req: reply), fail=errors.append)
es['get'](e, 'https://example.test/', received.append, 'image')
reply.finished.emit()
assert errors and not received
passed.append('stale responses ignored and HTTP-200 Token error rejected')

with tempfile.TemporaryDirectory(prefix='nlma-regression-', dir=tempfile.gettempdir()) as tmp:
    root = Path(tmp).resolve()
    assert root.parent == Path(tempfile.gettempdir()).resolve()
    cache = root / 'cache'
    cache.mkdir()
    ps['cache_root'] = lambda: cache

    def fixture():
        folder = cache / uuid.uuid4().hex
        folder.mkdir()
        source = folder / 'old.png'
        source.write_bytes(png(2, 2))
        source.with_suffix('.pgw').write_text('1\n0\n0\n-1\n10\n20')
        layer, logs = Layer(source), []
        p = NS(project=NS(fileName=lambda: str(root / 'case.qgz'), writePath=str, mapLayers=lambda: {'L1':layer}),
               log=lambda *a, **kw: logs.append((a, kw)), applying=False,
               canvas=NS(stopRendering=lambda: None, refresh=lambda: None),
               managed=lambda obj: True, owned_folders={folder}, preserved_sources=set())
        bind(p, ps, ['prune_caches'])
        e = NS(layer=lambda: layer, plugin=p, county='臺北市', version='報部版',
               count=0, folder=folder, pinned_sources=set(), visible=lambda: True,
               cancel_all=lambda: None)
        bind(e, es, ('fail', 'apply', 'discard'))
        p.engines = {'L1': e}
        return source, layer, p, e, logs

    def save(p, layer):
        doc = Document()
        element = doc.layer_element(layer)
        ps['save_snapshot'](p, layer, element, doc)
        doc.append(element)
        return doc

    source, layer, p, e, logs = fixture()
    saved = save(p, layer)
    assert saved.source() != source and saved.source().exists() and not e.pinned_sources
    snapshot_bytes = saved.source().read_bytes()
    image = png(512, 256)
    assert e.apply(image, (0, 0, 512, 256), (512, 256), 1, 3826)
    assert not source.exists() and saved.source().read_bytes() == snapshot_bytes
    assert Path(layer.source()).read_bytes() == image and layer.renderer().opacity() == 0.42
    assert layer.props[core.PROPERTY+'image_county'] == '臺北市'
    assert layer.crs_value == 'EPSG:3826'
    second = save(p, layer)
    third = save(p, layer)
    assert second.source() == third.source() and second.source() != saved.source()
    assert saved.source().read_bytes() == snapshot_bytes
    passed.append('writeMapLayer -> save -> pan: immutable snapshot survives live-frame pruning; deduplication')

    source, layer, p, e, logs = fixture()
    source.write_bytes(png(2, 2, 7))  # New content must exercise publishing, not deduplication.
    original_open = Path.open
    denied = []
    def deny_world(path, mode='r', *args, **kwargs):
        if mode == 'xb' and path.name == 'image.pgw':
            denied.append(True)
            raise OSError('Injected write failure')
        return original_open(path, mode, *args, **kwargs)
    with patch.object(Path, 'open', deny_world):
        failed_save = save(p, layer)
    assert denied and failed_save.source() == source and str(source.resolve()) in e.pinned_sources
    assert e.apply(image, (0, 0, 512, 256), (512, 256), 1, 3826)
    assert source.exists() and failed_save.source().exists()
    assert saved.source().read_bytes() == snapshot_bytes
    assert not list((root / 'snapshots').glob('*/.stage-*'))
    passed.append('world-file write failure leaves older snapshots intact and pins fallback live frame')

    source, layer, p, e, logs = fixture()
    duplicate = Layer(source)
    visible_layers = {'L1':layer, 'duplicate':duplicate}
    p.project.mapLayers = lambda: visible_layers
    assert e.apply(image, (0, 0, 512, 256), (512, 256), 1, 3826)
    assert source.exists()  # Another layer still references it.
    visible_layers.pop('duplicate')
    p.prune_caches()
    assert not source.exists()
    retired = cache/uuid.uuid4().hex
    retired.mkdir()
    (retired/'unused.png').write_bytes(png(2, 2))
    (retired/'unused.pgw').write_text('1\n0\n0\n-1\n0\n0')
    p.owned_folders.add(retired)
    legacy = cache/'legacy-session'
    legacy.mkdir()
    (legacy/'old.png').write_bytes(png(2, 2))
    p.prune_caches()
    assert not retired.exists() and (legacy/'old.png').exists() and saved.source().exists()
    passed.append('cache cleanup protects shared frames, legacy folders and snapshots; removes owned unused folders')

    for failure in ('source', 'style', 'crs', 'property', 'repaint'):
        source, layer, p, e, logs = fixture()
        old_props = dict(layer.props)
        layer.failures.add(failure)
        assert not e.apply(image, (0, 0, 512, 256), (512, 256), 1, 3825)
        assert layer.source() == str(source) and layer.crs_value == 'EPSG:3826'
        assert layer.renderer().opacity() == 0.42 and e.count == 0 and not p.applying
        assert layer.props[core.PROPERTY+'status'] == 'paused'
        for key in core.IMAGE_PROPERTIES:
            assert layer.customProperty(core.PROPERTY+key, None) == old_props.get(core.PROPERTY+key)
        assert '已還原' in layer.props[core.PROPERTY+'last_error']
    source, layer, p, e, logs = fixture()
    class BadStyle(Style):
        def writeToLayer(self, layer): raise RuntimeError('persistent fault')
    with patch.dict(es, QgsMapLayerStyle=BadStyle):
        assert not e.apply(image, (0, 0, 512, 256), (512, 256), 1, 3825)
    assert layer.props[core.PROPERTY+'image_state'] == 'uncertain'
    passed.append('five mutation failures restore source/CRS/style/opacity/provenance; failed rollback reports uncertainty')

    source, layer, p, e, logs = fixture()
    calls = []
    e.dispose = lambda: calls.append('dispose')
    p.selected_engine = lambda: e
    p.iface = NS(messageBar=lambda: NS(pushInfo=lambda *a: calls.append('info')))
    p.schedule = lambda: calls.append('schedule')
    def new_engine(plugin, obj):
        return NS(layer=lambda: obj, county=obj.customProperty(core.PROPERTY+'county'),
                  version=obj.customProperty(core.PROPERTY+'version'), pinned_sources=set(), folder=Path(obj.source()).parent)
    ps['Engine'] = new_engine
    ps['add_county'](p, '臺北市', '報部版')
    assert not calls and layer.renderer().opacity() == 0.42 and p.engines['L1'] is e
    with patch.dict(ps, Engine=lambda *a: (_ for _ in ()).throw(OSError('Injected'))):
        ps['add_county'](p, '金門縣', '公展版')
    assert not calls and p.engines['L1'] is e and layer.customProperty(core.PROPERTY+'county') == '臺北市'
    ps['add_county'](p, '金門縣', '公展版')
    assert calls == ['dispose', 'info', 'schedule'] and layer.renderer().opacity() == 0.7
    assert layer.source() == str(source) and '臺北市' in core.displayed_image(layer)
    e.county, e.version = '金門縣', '公展版'
    e.fail('Token 失效')
    assert '臺北市' in core.displayed_image(layer)
    assert layer.customProperty(core.PROPERTY+'county') == '金門縣'
    e.paused = False
    assert e.apply(image, (0, 0, 512, 256), (512, 256), 1, 3825)
    assert '金門縣' in core.displayed_image(layer) and '公開展覽' in core.displayed_image(layer)
    assert layer.crs_value == 'EPSG:3825' and layer.renderer().opacity() == 0.7
    passed.append('unchanged selection no-op; failed controller creation keeps old session; requested/displayed identity separation')

    key = ((0, 0, 512, 256), (512, 256), 192, 3826)
    requests, boots = [], []
    e = NS(closed=False, paused=False, booting=False, visible=lambda: True,
           view=lambda: (key, 1), last_key=None, token='fixture', acquired=1,
           reply=None, service_id=1, initialize=lambda: boots.append(True),
           get=lambda *a: requests.append(a), apply=lambda *a: True)
    es['draw'](e)
    assert len(requests) == 1 and not boots  # 1799 seconds old.
    requests.clear(); e.acquired = 0
    es['draw'](e)
    assert not requests and len(boots) == 1
    e.last_key = key; boots.clear()
    es['draw'](e)
    assert not requests and not boots  # Idle/same image does not renew.
    e.last_key = None; e.visible = lambda: False
    es['draw'](e)
    assert not requests and not boots
    e.visible = lambda: True; e.paused = True
    es['draw'](e)
    assert not requests and not boots
    cancels = []
    change = NS(visible=lambda: True, request_key=key, view=lambda: (key, 1),
                cancel_image=lambda: cancels.append('image'))
    es['view_changed'](change)
    assert not cancels
    change.view = lambda: (('new',), 1)
    es['view_changed'](change)
    assert cancels == ['image']
    passed.append('renew only on demand at 30 minutes; paused/hidden/unchanged views silent; unrelated change keeps request')

    source, layer, p, e, logs = fixture()
    render_enabled, in_scale, shown = [True], [True], [layer]
    layer.isInScaleRange = lambda scale: in_scale[0]
    p.project.layerTreeRoot = lambda: NS(findLayer=lambda _: NS(isVisible=lambda: True))
    p.canvas = NS(renderFlag=lambda: render_enabled[0], layers=lambda *a: shown, scale=lambda: 10000)
    e.layer_id = layer.id()
    assert es['visible'](e)
    render_enabled[0] = False
    assert not es['visible'](e)
    render_enabled[0], in_scale[0] = True, False
    assert not es['visible'](e)
    in_scale[0] = True; shown.clear()
    assert not es['visible'](e)
    passed.append('render disabled, scale-hidden and absent canvas layers do not request imagery')

    # Execute initGui: assertions check actual subscriptions, not source text.
    class Action:
        def __init__(self, *args): self.triggered = Signal()
        def setIcon(self, *args): pass
        def setToolTip(self, *args): pass
    project = NS(**{name: Signal() for name in ('layersAdded','layersWillBeRemoved','cleared',
                   'readProject','writeProject','writeMapLayer')})
    tree = NS(visibilityChanged=Signal())
    project.layerTreeRoot = lambda: tree
    canvas = NS(**{name: Signal() for name in ('extentsChanged','destinationCrsChanged',
                 'rotationChanged','layersChanged','renderStarting')})
    iface = NS(mainWindow=lambda: None, addPluginToMenu=lambda *a: None, addToolBarIcon=lambda *a: None)
    gui = NS(iface=iface, canvas=canvas, project=project, actions=[], connections=[],
             restore=lambda: None)
    for name in ('add_dialog','reconnect','pause','show_status','changed','layers_added','layers_removing','clear'):
        setattr(gui, name, lambda *a: None)
    gui.save_snapshot = MethodType(ps['save_snapshot'], gui)
    bind(gui, ps, ['connect'])
    with patch.dict(ps, QAction=Action, QIcon=lambda *a: None, __file__=str(SOURCE/'plugin.py')):
        ps['initGui'](gui)
    assert project.writeMapLayer.callbacks == [gui.save_snapshot]
    assert not project.writeProject.callbacks
    passed.append('actual initGui subscribes to writeMapLayer, not early writeProject')

    layers = {'L1': layer}
    created = []
    class RestoreEngine:
        def __init__(self, *args): created.append(self); self.closed = False
        def dispose(self): self.closed = True
    p = NS(alive=True, engines={}, catalog=[{'county':layer.customProperty(core.PROPERTY+'county'),
                                          'version':layer.customProperty(core.PROPERTY+'version')}],
           project=NS(mapLayers=lambda: layers), schedule=lambda: None,
           hide_band_legend=lambda layer: None,
           log=lambda *a, **k: None, timer=Timer(), prune_caches=lambda: None)
    bind(p, ps, ('managed','attach'))
    with patch.dict(ps, Engine=RestoreEngine):
        ps['restore'](p); ps['restore'](p)
    assert len(created) == 1 and len(p.engines) == 1
    ps['clear'](p)
    assert created[0].closed and not p.engines
    passed.append('idempotent restore and project-clear disposal')

print('PASS: %d regression groups' % len(passed))
for name in passed: print('  ' + name)
(WORK/'regressions.json').write_text(json.dumps(passed, indent=2), encoding='utf-8')
