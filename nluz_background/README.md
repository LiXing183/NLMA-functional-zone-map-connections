# NLMA國土功能分區圖連線

NLMA Functional Zone Map Connections — version 1.0.1, by Xing Li.

Display Taiwan NLMA draft functional zone maps in QGIS. Select the ministry-review or public-exhibition stage and a county/city. Pan or zoom the main map canvas to refresh. Internet access is required; no extra Python packages are needed beyond QGIS.

在 QGIS 載入臺灣 22 縣市的國土功能分區草案圖，支援「報部審議階段」及「公開展覽階段」。平移、縮放主畫布後自動更新影像；需要網際網路連線，無須額外安裝 Python 套件。

Use the green cloud/map toolbar button or the plugin menu. Default: Taipei City / ministry review, 70% opacity. The menu also provides pause, reconnect and connection status. Sessions older than 30 minutes renew only when a new image is needed.

從綠色雲端地圖工具列按鈕或外掛選單操作。預設臺北市、報部審議階段及 70% 不透明度；提供暫停、重新連線及連線狀態。Token 超過 30 分鐘後，等下次需要新影像時才更新。

**各直轄市、縣(市)國土功能分區圖皆為公開展覽草案，非依法核定及公告結果。**

Images are draft information, not legally approved or promulgated results. This independent plugin is not an official NLMA product. Its license does not establish permission to use third-party maps or a stable public API. Provider access restrictions still apply.

The maintainer reported successful operation of the code used in 1.0.0 on Windows / QGIS 4.2.3. Version 1.0.1 renames one local variable and adds bilingual descriptions; this revision has not been separately tested in a live QGIS session. Other declared versions and operating systems are not separately tested. Snapshots are local files under the QGIS profile and are not embedded in the QGZ. Custom QGIS proxy/authentication settings and independent layout/atlas imagery requests are not integrated.

維護者已回報 1.0.0 沿用的程式於 Windows／QGIS 4.2.3 操作正常，1.0.1 尚未另行實機測試。影像快照保存在本機 QGIS 設定目錄，未嵌入 QGZ；跨電腦使用時需另行處理快照。自訂代理、認證及版面配置／地圖集獨立取圖尚未整合。

See [使用說明.txt](使用說明.txt) for usage and limitations, [CHANGELOG.md](CHANGELOG.md) for changes and [LICENSE](LICENSE) for GPL-2.0-only terms.

[Project documentation](https://github.com/LiXing183/NLMA-functional-zone-map-connections#readme) · [Issues](https://github.com/LiXing183/NLMA-functional-zone-map-connections/issues)

Contact: li.xing.183.github@icloud.com

本外掛使用 Codex 生成。This plugin was generated using Codex.
