# Changelog

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
