import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from qgis.PyQt.QtCore import QObject, QTimer, QUrl, Qt
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkRequest
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsRasterLayer, QgsMapLayerStyle)
from .core import (TITLE, SERVICE, PROXY, PROPERTY, entry_url, parse_entry,
                   response_error, render_geometry, token_due, render_size, county_epsg,
                   IMAGE_PROPERTIES, displayed_image, version_label)
from .storage import png_size


def cache_root():
    root = Path(QgsApplication.qgisSettingsDirPath()) / 'nluz_background' / 'cache'
    root.mkdir(parents=True, exist_ok=True)
    return root


def placeholder(folder):
    path = folder / 'placeholder.png'
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    if not image.save(str(path), 'PNG'):
        raise OSError('Cannot create cache')
    path.with_suffix('.pgw').write_text('100\n0\n0\n-100\n13315050\n2824950\n', encoding='ascii')
    return path


class Engine(QObject):
    def __init__(self, plugin, layer):
        super().__init__(plugin.iface.mainWindow())
        self.plugin = plugin
        self.layer_id = layer.id()
        self.county = layer.customProperty(PROPERTY + 'county', '')
        self.version = layer.customProperty(PROPERTY + 'version', '')
        self.entry = entry_url(self.county, self.version)
        self.net = QNetworkAccessManager(self)
        self.token = None
        self.acquired = None
        self.service_id = None
        self.reply = None
        self.reply_kind = None
        self.epoch = 0
        self.image_epoch = 0
        self.closed = False
        self.paused = False
        self.booting = False
        self.last_key = None
        self.request_key = None
        self.pinned_sources = set()
        self.count = 0
        self.max_pixels = 4096
        self.folder = cache_root() / uuid.uuid4().hex
        self.folder.mkdir()
        self.plugin.owned_folders.add(self.folder)
        # Keep the restored source until a new image succeeds. It may be in a
        # previous run's cache; never delete arbitrary restored layer sources.
        if not layer.isValid():
            layer.setDataSource(str(placeholder(self.folder)), layer.name(), 'gdal')
            layer.setCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
            layer.setCustomProperty(PROPERTY + 'image_state', 'empty')

    def layer(self):
        return self.plugin.project.mapLayer(self.layer_id)

    def visible(self):
        node = self.plugin.project.layerTreeRoot().findLayer(self.layer_id)
        canvas, layer = self.plugin.canvas, self.layer()
        if node is None or not node.isVisible() or layer is None or not canvas.renderFlag():
            return False
        try:
            layers = canvas.layers(True)  # Include children of rendered group layers.
        except TypeError:
            layers = canvas.layers()
        return (any(item.id() == self.layer_id for item in layers)
                and layer.isInScaleRange(canvas.scale()))

    def cancel_image(self):
        self.image_epoch += 1
        self.request_key = None
        if self.reply is not None and self.reply_kind == 'image':
            old, self.reply = self.reply, None
            old.abort()

    def cancel_all(self):
        self.epoch += 1
        self.image_epoch += 1
        self.request_key = None
        old, self.reply = self.reply, None
        if old is not None:
            old.abort()
        self.booting = False

    def dispose(self):
        self.closed = True
        self.cancel_all()
        self.token = None
        self.acquired = None
        self.plugin.preserved_sources.update(self.pinned_sources)
        self.deleteLater()

    def fail(self, message, retained=True):
        self.paused = True
        self.cancel_all()
        layer = self.layer()
        if layer:
            layer.setCustomProperty(PROPERTY + 'status', 'paused')
            layer.setCustomProperty(PROPERTY + 'last_error', message)
            if not retained:
                layer.setCustomProperty(PROPERTY + 'image_state', 'uncertain')
        shown = displayed_image(layer) if layer else '圖層已移除'
        self.plugin.log('%s／%s：%s；已暫停。畫面：%s。' %
                        (self.county, version_label(self.version), message, shown), warning=True)

    def get(self, url, callback, kind, html=False):
        epoch, image_epoch = self.epoch, self.image_epoch
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b'Referer', self.entry.encode('ascii'))
        request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                             QNetworkRequest.CacheLoadControl.AlwaysNetwork)
        reply = self.net.get(request)
        self.reply, self.reply_kind = reply, kind
        timer = QTimer(reply)
        timer.setSingleShot(True)
        expired = [False]

        def timeout():
            expired[0] = True
            reply.abort()

        def finished():
            timer.stop()
            if self.reply is reply:
                self.reply = None
                self.reply_kind = None
                if kind == 'image':
                    self.request_key = None
            stale = (self.closed or epoch != self.epoch or
                     (kind == 'image' and image_epoch != self.image_epoch))
            if stale:
                reply.deleteLater()
                return
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            network_code = reply.error()
            data = bytes(reply.readAll())
            reply.deleteLater()
            if expired[0]:
                self.fail('請求超過 30 秒')
                return
            error = response_error(status, data, network_code, allow_html=html)
            if error:
                self.fail(error)
                return
            try:
                callback(data)
            except Exception:
                # Avoid QGIS console tracebacks containing token-bearing locals.
                self.fail('回應解析、圖層設定或本機影像更新失敗；未輸出憑證')

        reply.finished.connect(finished)
        timer.timeout.connect(timeout)
        timer.start(30000)

    def reconnect(self):
        self.cancel_all()
        self.paused = False
        self.token = None
        self.acquired = None
        self.last_key = None
        layer = self.layer()
        if layer:
            layer.setCustomProperty(PROPERTY + 'status', 'waiting')
            layer.setCustomProperty(PROPERTY + 'last_error', '')
        if self.visible():
            self.initialize()
        else:
            self.plugin.log('%s：已準備重新連線，勾選圖層並展圖時執行。' % self.county)

    def initialize(self):
        if self.closed or self.paused or self.booting or not self.visible():
            return
        self.booting = True
        layer = self.layer()
        if layer:
            layer.setCustomProperty(PROPERTY + 'status', 'connecting')
        self.plugin.log('%s %s：取得新工作階段並驗證服務。' % (self.county, self.version))
        self.get(self.entry, self.home_loaded, 'session', html=True)

    def home_loaded(self, data):
        try:
            self.token, self.service_id = parse_entry(data, self.county, self.version)
        except ValueError as error:
            # Only our fixed parser messages, not JSON / network exceptions.
            if type(error) is ValueError:
                self.fail(str(error))
            else:
                self.fail('官方頁面圖層設定解析失敗')
            return
        self.acquired = time.monotonic()
        self.get(PROXY + SERVICE + '?' + urlencode({'f': 'json', 'token': self.token}),
                 self.metadata_loaded, 'session')

    def metadata_loaded(self, data):
        info = json.loads(data)
        if not any(
            service_layer.get('id') == self.service_id
            for service_layer in info.get('layers', [])
        ):
            self.fail('服務未包含官方頁面指定的圖層')
            return
        sr = info.get('spatialReference', {})
        if sr.get('latestWkid', sr.get('wkid')) not in (3857, 102100, 102113):
            self.fail('服務座標系統已變更，請停止使用此版本')
            return
        self.max_pixels = min(4096, int(info.get('maxImageWidth', 0)),
                              int(info.get('maxImageHeight', 0)))
        if self.max_pixels < 512:
            self.fail('服務出圖尺寸限制不符合要求')
            return
        self.booting = False
        layer = self.layer()
        if layer:
            layer.setCustomProperty(PROPERTY + 'service_id', self.service_id)
        self.plugin.schedule()

    def view(self):
        canvas = self.plugin.canvas
        rect = canvas.mapSettings().visibleExtent()
        canvas_crs = canvas.mapSettings().destinationCrs()
        image_epsg = county_epsg(self.county)
        transform = QgsCoordinateTransform(canvas_crs,
                                            QgsCoordinateReferenceSystem('EPSG:%d' % image_epsg),
                                            self.plugin.project)
        rect = transform.transformBoundingBox(rect)
        pixels, dpi = render_size(canvas.width(), canvas.height(),
                                  canvas.devicePixelRatioF(), self.max_pixels)
        bbox, size, resolution = render_geometry((rect.xMinimum(), rect.yMinimum(),
                                                 rect.xMaximum(), rect.yMaximum()), pixels)
        return (bbox, size, dpi, image_epsg), resolution

    def view_changed(self):
        if not self.visible():
            self.cancel_image()
            if self.booting:
                self.cancel_all()
        elif self.request_key is not None:
            try:
                key, _ = self.view()
                if key != self.request_key:
                    self.cancel_image()
            except Exception:
                self.cancel_image()

    def draw(self):
        if self.closed or self.paused or self.booting or not self.visible():
            return
        try:
            key, resolution = self.view()
        except Exception:
            self.fail('畫布範圍無法轉換為有效出圖座標')
            return
        bbox, size, dpi, image_epsg = key
        if key == self.last_key:
            return
        if not self.token or token_due(self.acquired, time.monotonic()):
            self.last_key = None
            self.initialize()
            return
        if self.reply is not None:
            return
        query = {'bbox': ','.join(format(v, '.15g') for v in bbox), 'bboxSR': image_epsg,
                 'imageSR': image_epsg, 'size': '%d,%d' % size, 'dpi': dpi,
                 'format': 'png32', 'transparent': 'true',
                 'layers': 'show:%d' % self.service_id, 'f': 'image', 'token': self.token}

        def loaded(data):
            if self.apply(data, bbox, size, resolution, image_epsg):
                self.last_key = key

        self.request_key = key
        self.get(PROXY + SERVICE + '/export?' + urlencode(query), loaded, 'image')

    def apply(self, data, bbox, size, resolution, image_epsg):
        if not self.visible():
            return False
        try:
            if png_size(data) != size:
                raise ValueError('Unexpected image size')
        except ValueError:
            self.fail('未取得有效且尺寸正確的 PNG；可能是工作階段失效')
            return False
        image = QImage.fromData(data)
        if image.isNull() or (image.width(), image.height()) != size:
            self.fail('未取得有效且尺寸正確的 PNG；可能是工作階段失效')
            return False
        del image  # Raw validated PNG bytes avoid UI-thread recompression.
        png = self.folder / ('frame_' + uuid.uuid4().hex + '.png')
        world = (resolution, 0, 0, -resolution, bbox[0] + resolution / 2,
                 bbox[3] - resolution / 2)
        try:
            png.write_bytes(data)
            png.with_suffix('.pgw').write_text('\n'.join(format(v, '.17g') for v in world), encoding='ascii')
        except OSError:
            self.discard(png)
            self.fail('無法寫入本機影像或定位檔')
            return False
        test = QgsRasterLayer(str(png), 'NLUZ validation', 'gdal')
        if not test.isValid():
            test = None
            self.discard(png)
            self.fail('本機 GDAL 無法載入影像')
            return False
        test = None
        layer = self.layer()
        if not layer:
            self.discard(png)
            return False
        old = layer.source()
        old_crs = QgsCoordinateReferenceSystem(layer.crs())
        opacity = layer.renderer().opacity()
        old_renderer = layer.renderer().clone()
        style = QgsMapLayerStyle()
        style.readFromLayer(layer)
        if not style.isValid():
            self.discard(png)
            self.fail('無法保存現有圖層樣式，已取消更新')
            return False
        keys = IMAGE_PROPERTIES + ('status', 'last_error', 'updates')
        old_properties = {key: layer.customProperty(PROPERTY + key, None) for key in keys}
        self.plugin.canvas.stopRendering()
        self.plugin.applying = True
        try:
            layer.setDataSource(str(png), layer.name(), 'gdal')
            if not layer.isValid():
                raise ValueError('Invalid replacement')
            style.writeToLayer(layer)
            layer.setCrs(QgsCoordinateReferenceSystem('EPSG:%d' % image_epsg))
            layer.renderer().setOpacity(opacity)
            values = {'status': 'connected', 'last_error': '', 'updates': self.count + 1,
                      'image_state': 'ready', 'image_county': self.county,
                      'image_version': self.version, 'image_crs': 'EPSG:%d' % image_epsg,
                      'image_bbox': json.dumps(bbox), 'image_size': json.dumps(size),
                      'image_updated_at': datetime.now(timezone.utc).isoformat()}
            for key, value in values.items():
                layer.setCustomProperty(PROPERTY + key, value)
            layer.triggerRepaint()
        except Exception:
            # Every mutation after source replacement is in this transaction.
            restored = True
            operations = [lambda: layer.setDataSource(old, layer.name(), 'gdal'),
                          lambda: style.writeToLayer(layer),
                          lambda: layer.setCrs(old_crs),
                          lambda: layer.setRenderer(old_renderer),
                          lambda: layer.renderer().setOpacity(opacity)]
            for operation in operations:
                try:
                    operation()
                except Exception:
                    restored = False
            for key, value in old_properties.items():
                try:
                    if value is None:
                        layer.removeCustomProperty(PROPERTY + key)
                    else:
                        layer.setCustomProperty(PROPERTY + key, value)
                except Exception:
                    restored = False
            restored = restored and layer.isValid() and layer.source() == old and layer.crs() == old_crs
            if restored:
                self.discard(png)
            self.fail('影像更新失敗，已還原原影像、座標及樣式' if restored
                      else '影像更新失敗，未能完整還原；請重新連線', retained=restored)
            self.plugin.canvas.refresh()
            return False
        finally:
            self.plugin.applying = False
        self.count += 1
        self.plugin.canvas.refresh()
        self.plugin.log('%s %s：展圖成功 #%d，%d×%d，%.2f 公尺／像素，EPSG:%d。' %
                        (self.county, self.version, self.count, size[0], size[1], resolution, image_epsg))
        # Protect other layers referencing a frame, saved fallbacks and legacy
        # sessions. Only directories created in this plugin run are eligible.
        self.plugin.prune_caches()
        return True

    def discard(self, png):
        # Only unreferenced candidates created in this controller's own folder.
        if png.parent.resolve() != self.folder.resolve():
            return
        for path in (png, png.with_suffix('.pgw')):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
