# Changelog

## 1.0.2

- Raise `qgisMaximumVersion` from 4.2.99 to 4.99 so QGIS 4.4 and later 4.x releases accept the plugin. The previous 4.2.99 ceiling blocked installation on QGIS 4.4.
- No runtime code changes: all Python modules and bundled map configuration are identical to 1.0.1. The code already uses the `qgis.PyQt` shim and fully scoped Qt enums, as Qt6/QGIS 4 requires.
- Change the authorship note to "made with Claude Code".
- Maintainer installed and tested 1.0.2 on Windows 11 with QGIS 4.4.0 (Qt 6.11.3).

- 將 `qgisMaximumVersion` 由 4.2.99 改為 4.99，使 QGIS 4.4 及後續 4.x 版本可安裝；原上限 4.2.99 使 QGIS 4.4 無法使用。
- 功能程式未變更：所有 Python 模組與內附圖資設定均與 1.0.1 相同；程式原已使用 `qgis.PyQt` 相容層及完整限定的 Qt 列舉，符合 Qt6／QGIS 4 要求。
- 製作聲明改為「透過 Claude Code 製作」。
- 維護者已於 Windows 11／QGIS 4.4.0（Qt 6.11.3）安裝並測試 1.0.2。

## 1.0.1

- Fix Flake8 E741 in `engine.py`: rename the ambiguous local variable `l` to `service_layer`, with no change to the service-layer validation logic.
- Add Chinese text to the plugin summary and About, with English first and Chinese second.
- Update the package version and documentation for resubmission.

- 修正 `engine.py` 的 Flake8 E741：將易混淆的區域變數 `l` 改為 `service_layer`，服務圖層驗證邏輯不變。
- 外掛簡介與 About 補上中文說明，英文在前、中文在後。
- 更新套件版本及文件，供重新提交。

## 1.0.0

First publication package, based on the user-tested 0.2.2 build.

- QGIS display name: NLMA國土功能分區圖連線; independent repository: NLMA-functional-zone-map-connections.
- Complete English description, author contact, homepage, source repository, issue tracker, tags and license statement.
- Add bilingual README, detailed usage/limitations, validation notes and reproducible release packaging.
- Record maintainer confirmation of successful operation on Windows with QGIS 4.2.3.
- Runtime Python source and bundled map configuration are unchanged from 0.2.2.

## 0.2.2 — Local test release

- Green cloud and zoning-map SVG icon; checked at small sizes on light/dark backgrounds.

## 0.2.1 — Local test release

- Hide RGB band legend rows while preserving the renderer and project layer-tree properties.

## 0.2.0 — Local test release

- Save immutable georeferenced image snapshots at the per-layer project-write event.
- Protect saved snapshots and shared images when pruning current-session caches.
- Preserve source, CRS, style, opacity and image identity on update failure; distinguish incomplete rollback.
- Use rectangular imagery with matching extent/pixel aspect ratios and avoid redundant image recompression.
- Renew sessions on image demand after 30 minutes; retain error warnings, pause and manual reconnection.
- Preserve county/stage selection, defaults, opacity behavior and EPSG:3825/3826 selection.
