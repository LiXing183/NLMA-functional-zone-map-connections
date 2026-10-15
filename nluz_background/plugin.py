import json
import uuid
from pathlib import Path

from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QComboBox, QLabel,
                                QDialogButtonBox, QMessageBox)
try:
    from qgis.PyQt.QtGui import QAction, QIcon
except ImportError:
    from qgis.PyQt.QtWidgets import QAction
    from qgis.PyQt.QtGui import QIcon
from qgis.core import (QgsProject, QgsRasterLayer, QgsCoordinateReferenceSystem,
                       QgsMessageLog, QgsMapLayerLegendUtils, Qgis)
from .core import TITLE, PROPERTY, LAYER_NAME, announcement_text, displayed_image, version_label
from .engine import Engine, cache_root, placeholder
from .storage import snapshot


class Plugin:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.project = QgsProject.instance()
        self.engines = {}
        self.owned_folders = set()
        self.preserved_sources = set()
        self.connections = []
        self.actions = []
        self.applying = False
        self.alive = False
        self.timer = QTimer(iface.mainWindow())
        self.timer.setSingleShot(True)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self.draw)
        self.catalog = json.loads(Path(__file__).with_name('counties.json').read_text(encoding='utf-8-sig'))
        self.county_order = json.loads(Path(__file__).with_name('county_order.json').read_text(encoding='utf-8'))
        self.announcements = json.loads(Path(__file__).with_name('announcements.json').read_text(encoding='utf-8'))

    def connect(self, signal, method):
        signal.connect(method)
        self.connections.append((signal, method))

    def initGui(self):
        self.alive = True
        # Avoid running the previous standalone test at the same time.
        old = getattr(self.iface, '_nluz_dynamic_test', None)
        if old:
            old.shutdown()
        for title, callback in [('載入／變更縣市…', self.add_dialog),
                                 ('重新連線', self.reconnect),
                                 ('暫停連線', self.pause),
                                 ('連線狀態', self.show_status)]:
            action = QAction(title, self.iface.mainWindow())
            action.triggered.connect(callback)
            self.iface.addPluginToMenu(TITLE, action)
            self.actions.append(action)
        self.toolbar_action = self.actions[0]
        self.toolbar_action.setIcon(QIcon(str(Path(__file__).with_name('icon.svg'))))
        self.toolbar_action.setToolTip(TITLE + '：載入／變更縣市')
        self.iface.addToolBarIcon(self.toolbar_action)
        for signal in (self.canvas.extentsChanged, self.canvas.destinationCrsChanged,
                       self.canvas.rotationChanged, self.canvas.layersChanged,
                       self.canvas.renderStarting):
            self.connect(signal, self.changed)
        self.connect(self.project.layerTreeRoot().visibilityChanged, self.changed)
        self.connect(self.project.layersAdded, self.layers_added)
        self.connect(self.project.layersWillBeRemoved, self.layers_removing)
        self.connect(self.project.cleared, self.clear)
        self.connect(self.project.readProject, self.restore)
        self.connect(self.project.writeMapLayer, self.save_snapshot)
        # Also restore when enabled after the project has already opened.
        self.restore()

    def log(self, message, warning=False, reconnect=True):
        level = Qgis.MessageLevel.Warning if warning else Qgis.MessageLevel.Info
        QgsMessageLog.logMessage(message, TITLE, level)
        if warning:
            suffix = ' 使用外掛選單「重新連線」重試。' if reconnect else ''
            self.iface.messageBar().pushWarning(TITLE, message + suffix)

    def managed(self, layer):
        return (isinstance(layer, QgsRasterLayer) and
                str(layer.customProperty(PROPERTY + 'enabled', '0')) == '1')

    def attach(self, layer):
        if not self.managed(layer):
            return
        self.hide_band_legend(layer)
        if layer.id() in self.engines:
            return
        county = str(layer.customProperty(PROPERTY + 'county', ''))
        version = str(layer.customProperty(PROPERTY + 'version', ''))
        if not any(r['county'] == county and r['version'] == version for r in self.catalog):
            self.log('專案中的 NLUZ 縣市／版本不在官方清單中，未自動連線。', True)
            return
        try:
            layer.setName(LAYER_NAME)
            self.engines[layer.id()] = Engine(self, layer)
        except Exception:
            self.log('無法建立 NLUZ 本機快取，請檢查 QGIS 設定目錄權限。', True)

    def hide_band_legend(self, layer):
        """Persist an empty legend for this layer without changing its renderer."""
        if not self.managed(layer):
            return
        node = self.project.layerTreeRoot().findLayer(layer.id())
        # layersAdded may precede insertion into the layer tree. The debounced
        # draw retries after insertion; readProject also reapplies to old projects.
        if node is None or node.customProperty('legend/node-order', '') == 'empty':
            return
        QgsMapLayerLegendUtils.setLegendNodeOrder(node, [])
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())

    def restore(self, *args):
        if not self.alive:
            return
        for layer in self.project.mapLayers().values():
            self.attach(layer)
        self.schedule()

    def layers_added(self, layers):
        # Project reading may add layers before readProject is emitted. Delay
        # network work until the normal debounce / final restoration phase.
        for layer in layers:
            self.attach(layer)
        self.schedule()

    def layers_removing(self, ids):
        for layer_id in ids:
            engine = self.engines.pop(layer_id, None)
            if engine:
                engine.dispose()

    def clear(self, *args):
        self.timer.stop()
        for engine in list(self.engines.values()):
            engine.dispose()
        self.engines.clear()
        self.prune_caches()

    def prune_caches(self):
        """Only reclaim this plugin run's files; never scan old cache/snapshots."""
        protected = {Path(source).resolve() for source in self.preserved_sources}
        for engine in self.engines.values():
            protected.update(Path(source).resolve() for source in engine.pinned_sources)
        for layer in self.project.mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                try:
                    protected.add(Path(layer.source()).resolve())
                except (OSError, ValueError):
                    pass
        active = {engine.folder.resolve() for engine in self.engines.values()}
        try:
            root = cache_root().resolve()
        except OSError:
            return
        for folder in list(self.owned_folders):
            try:
                if folder.is_symlink() or folder.resolve().parent != root:
                    continue
                for path in folder.iterdir():
                    if (path.suffix in ('.png', '.pgw')
                            and path.with_suffix('.png').resolve() not in protected):
                        try:
                            path.unlink()
                        except OSError:
                            pass
                if folder.resolve() not in active and not any(folder.iterdir()):
                    folder.rmdir()
                    self.owned_folders.discard(folder)
            except OSError:
                pass

    def schedule(self):
        if self.alive and not self.applying:
            self.timer.start()

    def changed(self, *args):
        if self.applying or not self.alive:
            return
        for engine in self.engines.values():
            engine.view_changed()
        self.schedule()

    def draw(self):
        if not self.alive:
            return
        for engine in list(self.engines.values()):
            self.hide_band_legend(engine.layer())
            engine.draw()

    def selected_engine(self):
        layer = self.iface.activeLayer()
        if layer and layer.id() in self.engines:
            return self.engines[layer.id()]
        return next(iter(self.engines.values()), None)

    def add_dialog(self, *args):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle(TITLE)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('選擇版本與縣市'))
        county_box, version_box = QComboBox(), QComboBox()
        available = {r['county'] for r in self.catalog}
        county_box.addItems([name for name in self.county_order if name in available])
        county_box.setCurrentText('臺北市')
        version_box.addItem('報部審議階段', '報部版')
        version_box.addItem('公開展覽階段', '公展版')
        version_box.setCurrentIndex(0)
        existing = self.selected_engine()
        if existing:
            county_box.setCurrentText(existing.county)
            index = version_box.findData(existing.version)
            if index >= 0:
                version_box.setCurrentIndex(index)
        layout.addWidget(version_box)
        layout.addWidget(county_box)
        announcement = QLabel()
        announcement.setWordWrap(True)
        announcement.setMinimumWidth(420)
        layout.addWidget(announcement)

        def update_announcement(*args):
            announcement.setText(announcement_text(self.announcements,
                                                   county_box.currentText(), version_box.currentData()))

        county_box.currentTextChanged.connect(update_announcement)
        version_box.currentTextChanged.connect(update_announcement)
        update_announcement()
        notice = QLabel('各直轄市、縣(市)國土功能分區圖皆為公開展覽草案，非依法核定及公告結果')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.add_county(county_box.currentText(), version_box.currentData())

    def add_county(self, county, version):
        existing = self.selected_engine()
        if existing:
            layer = existing.layer()
            if layer:
                if county == existing.county and version == existing.version:
                    return
                previous = {key: layer.customProperty(PROPERTY + key, '')
                            for key in ('county', 'version', 'status', 'last_error')}
                opacity = layer.renderer().opacity()
                try:
                    layer.setCustomProperty(PROPERTY + 'county', county)
                    layer.setCustomProperty(PROPERTY + 'version', version)
                    new_engine = Engine(self, layer)
                except Exception:
                    for key, value in previous.items():
                        layer.setCustomProperty(PROPERTY + key, value)
                    layer.renderer().setOpacity(opacity)
                    self.log('無法建立新連線，保留原縣市及影像。', True)
                    return
                existing.dispose()
                self.engines[layer.id()] = new_engine
                layer.setName(LAYER_NAME)
                layer.renderer().setOpacity(0.7)
                layer.triggerRepaint()
                layer.setCustomProperty(PROPERTY + 'status', 'switching')
                layer.setCustomProperty(PROPERTY + 'last_error', '')
                message = '切換至 %s／%s；目前畫面：%s。' % (county, version_label(version), displayed_image(layer))
                self.log(message)
                self.iface.messageBar().pushInfo(TITLE, message)
                self.schedule()
                return
        try:
            folder = cache_root() / uuid.uuid4().hex
            folder.mkdir()
            self.owned_folders.add(folder)
            layer = QgsRasterLayer(str(placeholder(folder)), LAYER_NAME, 'gdal')
            if not layer.isValid():
                raise ValueError('Invalid placeholder')
            layer.setCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
            layer.renderer().setOpacity(0.7)
            for key, value in {'enabled': '1', 'county': county, 'version': version,
                               'status': 'waiting', 'image_state': 'empty'}.items():
                layer.setCustomProperty(PROPERTY + key, value)
            self.project.addMapLayer(layer)
            self.attach(layer)
            self.log('%s %s：已加入；請移至該縣市範圍查看。' % (county, version))
            self.schedule()
        except Exception:
            self.log('建立圖層失敗，請檢查本機快取目錄權限。', True)

    def reconnect(self, *args):
        for engine in self.engines.values():
            engine.reconnect()

    def pause(self, *args):
        self.timer.stop()
        for engine in self.engines.values():
            engine.cancel_all()
            engine.paused = True
            layer = engine.layer()
            if layer:
                layer.setCustomProperty(PROPERTY + 'status', 'paused')
        self.log('NLUZ 已暫停；保留最後影像。重新連線可恢復。')

    def show_status(self, *args):
        lines = []
        for engine in self.engines.values():
            layer = engine.layer()
            if layer:
                status = layer.customProperty(PROPERTY + 'status', 'waiting')
                status = {'waiting': '等待展圖', 'connecting': '連線中', 'connected': '已連線',
                          'paused': '已暫停', 'switching': '切換中'}.get(status, status)
                lines.append('選擇：%s／%s\n畫面：%s\n%s；本次更新 %d 次\n%s' %
                             (engine.county, version_label(engine.version), displayed_image(layer), status, engine.count,
                              layer.customProperty(PROPERTY + 'last_error', '')))
        QMessageBox.information(self.iface.mainWindow(), TITLE, '\n\n'.join(lines) or '尚未加入圖層。')

    def save_snapshot(self, layer, element, document):
        """writeMapLayer provides a populated element, before project commit."""
        if not self.managed(layer):
            return
        engine = self.engines.get(layer.id())
        source = layer.source()
        pin = str(Path(source).resolve())
        was_pinned = engine is not None and pin in engine.pinned_sources
        # Protect the serialized live frame even if snapshot/DOM writing fails.
        # Never unpin it: a failed save or backup may still reference that file.
        if engine:
            engine.pinned_sources.add(pin)
        try:
            name = self.project.fileName()
            if not name:
                raise ValueError('Missing project filename')
            target = snapshot(source, cache_root().parent / 'snapshots', name, layer.crs().authid())
            datasource = element.firstChildElement('datasource')
            if datasource.isNull():
                raise ValueError('Missing datasource element')
            replacement = document.createElement('datasource')
            replacement.appendChild(document.createTextNode(self.project.writePath(str(target))))
            element.replaceChild(replacement, datasource)
            if engine and not was_pinned:
                engine.pinned_sources.discard(pin)
        except Exception:
            self.log('恢復快照保存失敗，已保留目前影像檔；請檢查磁碟空間後再次儲存專案。', True, reconnect=False)

    def unload(self):
        self.alive = False
        self.clear()
        for signal, method in self.connections:
            try:
                signal.disconnect(method)
            except (TypeError, RuntimeError):
                pass
        self.connections.clear()
        self.timer.deleteLater()
        if hasattr(self, 'toolbar_action'):
            self.iface.removeToolBarIcon(self.toolbar_action)
        for action in self.actions:
            self.iface.removePluginMenu(TITLE, action)
            action.deleteLater()
        self.actions.clear()
        # Saved snapshots / current rasters remain, so disabling the plugin
        # cannot break the user's project or remove the last successful image.
