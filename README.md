# NLMA國土功能分區圖連線 / NLMA Functional Zone Map Connections

<img src="nluz_background/icon.svg" width="80" height="80" alt="NLMA functional zone map icon">

A QGIS plugin for displaying Taiwan NLMA draft functional zone maps, selecting counties and review stages, and refreshing imagery as the main map canvas changes.

在 QGIS 載入臺灣國土功能分區草案圖，可選擇縣市與報部審議／公開展覽階段，並隨主畫布平移、縮放自動更新影像。

**Version:** 1.0.1 · **QGIS metadata compatibility:** 3.24.0–4.2.99 · **User-tested baseline:** Windows / QGIS 4.2.3 · **License:** GPL-2.0-only

Repository name: `NLMA-functional-zone-map-connections`. QGIS display name: **NLMA國土功能分區圖連線**.

## 功能 / Features

- 選擇 22 縣市的「報部審議階段」或「公開展覽階段」；預設為臺北市、報部審議階段。
- 透過上方工具列或外掛選單操作，固定使用 `NLMA_國土功能分區` 圖層。
- 主畫布平移、縮放後自動更新影像；切換縣市沿用原圖層，預設不透明度 70%。
- 隱藏 Band 1／2／3 圖例，保持圖層清單簡潔。
- 臺灣本島出圖採 EPSG:3826；澎湖、金門、連江採 EPSG:3825。
- 工作階段超過 30 分鐘，等下次需要新影像才更新；閒置時不輪詢。
- 連線失敗提示、暫停與重新連線；保存影像快照，重開專案後恢復連線。

County/stage selection, dynamic main-canvas imagery, demand-driven session renewal, connection diagnostics and local project snapshots. No additional Python packages are required beyond QGIS.

## 安裝 / Installation

1. Download `NLMA-functional-zone-map-connections-1.0.1.zip` from this project's Releases when published.
2. In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP**.
3. Install the ZIP, restart QGIS and enable **NLMA國土功能分區圖連線**.

QGIS 官方外掛庫核准上架後，亦可直接搜尋中文名稱安裝。GitHub 自動產生的 Source code ZIP 是原始碼，請勿當成 QGIS 安裝包。

The installable ZIP contains one `nluz_background/` directory. The internal package name is retained from local test releases so existing installations and saved project properties remain compatible.

## 操作 / Usage

1. Click the green cloud/map toolbar button, or choose **載入／變更縣市…** from the plugin menu.
2. Select the stage first, then the county/city, and confirm. Pan or locate the map to the selected county.
3. Pan or zoom; after approximately 0.8 seconds of inactivity, the main-canvas extent is requested.
4. On a connection error, read the warning and use **重新連線**. **連線狀態** distinguishes the requested county/stage from the image currently displayed.
5. Save the QGIS project after a successful render. When upgrading from a test release, reopen and save once with this version.

Only changing the county or stage resets opacity to 70%. Ordinary refreshes retain user-adjusted opacity. Opening the selector and confirming unchanged values does not reconnect.

- [中文操作與保存說明 / Detailed guide](nluz_background/使用說明.txt)
- [驗證範圍 / Validation](docs/VALIDATION.md)
- [版本更新 / Changelog](CHANGELOG.md)

## 資料來源與限制 / Data and limitations

Source: [內政部國土管理署國土功能分區圖公開展覽資訊](https://nluz.nlma.gov.tw/ex3s/).

**各直轄市、縣(市)國土功能分區圖皆為公開展覽草案，非依法核定及公告結果。**

- Taiwan only; actual map requests require Internet access. This independent tool is not an official NLMA product. The code license does not grant rights to third-party maps or services.
- Requests use the public website's session and map proxy. Access, rate limits, available layers and site behavior are controlled by the provider. A working request does not establish stable API access or permission for continuing third-party use.
- The 30-minute interval is a local renewal threshold, not a verified natural token lifetime. Authentication or session failures pause requests; they do not trigger indefinite automatic retries.
- Tokens and cookies stay in memory. The plugin does not bundle credentials, login accounts, downloaded map images or user projects.
- Independent Qt network managers do not integrate custom QGIS proxy/authentication settings. Corporate proxy environments may require additional integration.
- The layer contains the last successful main-canvas image. Print layouts, atlases and secondary map views do not independently request imagery.
- PNG/PGW snapshots live in the QGIS profile under `nluz_background/snapshots`; they are not embedded in the QGZ. Moving a project to another computer also requires its snapshot files. Existing snapshots are not automatically removed.
- County order and announcement text are bundled snapshots, not live announcement feeds.
- The maintainer reported successful functionality of the code used in 1.0.0 on Windows with QGIS 4.2.3. Version 1.0.1 fixes a local variable name and adds bilingual descriptions; this revision has not been separately tested in a live QGIS session. Linux, macOS and other declared QGIS versions have not been separately verified; the metadata range is not a claim that every version was tested.

## 開發與封裝 / Development

From the repository root, with Python 3.8 or later:

```console
python tests/test_regressions.py
python tools/build_release.py
```

Tests use fake QGIS objects and real temporary files; they do not replace QGIS runtime validation or contact the map service. Packaging uses only the Python standard library. The generated ZIP and checksum are written to `dist/` and should be attached to a Release rather than committed as source.

## 問題回報 / Issues

Use [GitHub Issues](https://github.com/LiXing183/NLMA-functional-zone-map-connections/issues). Include plugin/QGIS versions, operating system, county/stage, reproduction steps and the warning text. Do not include tokens, cookies or URLs containing session credentials.

## 授權 / License

This project's code and original icon are distributed under **GNU General Public License version 2 (GPL-2.0-only)**. See [LICENSE](LICENSE). Third-party data and service rights remain with their respective providers.

Author: Xing Li.  
Maintainer email: li.xing.183.github@icloud.com

本外掛使用 Codex 生成。This plugin was generated using Codex.
