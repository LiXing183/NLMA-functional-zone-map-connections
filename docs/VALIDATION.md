# 驗證紀錄 / Validation

## 實機回報

發布準備時，維護者在對話中確認「測試功能已正常運作」，並確認測試版本為 **QGIS 4.2.3**。操作環境為 Windows。

This is a maintainer/user report, not an automated QGIS runtime result. No detailed new per-scenario test record was supplied. The 1.0.0 publication package keeps the runtime Python files from the confirmed 0.2.2 build unchanged.

Version 1.0.1 changes only a comprehension-local variable name in the runtime code; the other four Python modules and bundled map configuration remain byte-identical to 1.0.0. An AST comparison confirms that the variable rename is the only runtime code change. Version 1.0.1 has not been separately tested in a live QGIS session.

1.0.1 的功能程式僅修改一處推導式區域變數名稱，其餘四個 Python 模組及圖資設定均與 1.0.0 相同。已比對語法樹確認變更範圍；本修訂版尚未另行實機測試。

## 可重現的離線檢查

`python tests/test_regressions.py` executes 12 regression groups with fake QGIS objects and actual temporary image/world files and XML serialization:

- Session renewal threshold and authentication/transport error classification.
- Rectangular extent/pixel geometry and pixel-center georeferencing.
- Stale response rejection and HTTP-200 responses containing token errors.
- Project-write snapshot handling, continued panning and content deduplication.
- Snapshot write failure and preservation of prior snapshots/fallback frames.
- Cache pruning restrictions and preservation of shared/legacy image sources.
- Rollback of source, CRS, style, opacity and image provenance after injected failures.
- Unchanged selector no-op, controller-creation failure and requested/displayed image identity.
- Idle, paused, hidden and unchanged views; demand-driven renewal after 30 minutes.
- Disabled canvas rendering, scale-hidden layers and layers absent from the main canvas.
- Registration of the per-layer project-write event.
- Idempotent restoration and disposal on project clear.

`python tools/build_release.py` validates metadata, Python syntax, JSON catalogs, icon XML, documentation links and ZIP layout, then verifies archive/source byte equality. It does not validate that GitHub URLs are already public or submit anything to QGIS.

## 本機發布檢查 / Local release checks

For version 1.0.1, all 12 offline regression groups passed again on 2026-10-16. Package metadata, English-before-Chinese ordering, source/archive equality and ZIP integrity were checked. The ambiguous variable `l` in `engine.py` was renamed to `service_layer`.

- Bandit 1.9.4: no findings and no scan errors in the plugin source.
- detect-secrets 1.5.0: no candidates in the plugin directory, using `--all-files --no-verify` (no network verification of potential secrets).
- Flake8 7.4.1, with isolated default rules: zero E741 findings. There are 82 other findings — 77 long lines (E501), four continuation-indentation issues (E127/E128) and one unused import (F401). No undefined-name or syntax diagnostics were reported. These other suggestions remain; this revision addresses the single issue identified in the supplied QGIS scan.

2026-10-16 重新執行的 12 組離線回歸均通過，並檢查封裝及中英文順序。E741 已修正，安全與機密資訊掃描未發現問題。完整預設 Flake8 仍有 82 項其他建議；這與截圖中的 QGIS 掃描結果不同，不宣稱所有 Flake8 規則均已通過。

These local tools do not prove the absence of defects or replace the upload-time scan. [QGIS's scanner documentation](https://plugins.qgis.org/docs/security-scanning/tools) describes Flake8 findings as informational. The machine-readable local result is in [local_checks.json](local_checks.json).

## QGIS 上傳掃描 / Uploaded-version scan

The screenshots supplied by the maintainer show the 1.0.0 upload under plugin ID 6636: four checks passed, one informational item (Flake8 E741 in `engine.py` line 211), zero warnings and zero critical findings. The page also says that no public version is available yet. This is evidence for the uploaded 1.0.0 package, not a scan of 1.0.1.

使用者提供的 1.0.0 掃描截圖顯示 4 項通過、1 項資訊提示、0 項警告、0 項重大問題；頁面當時尚無公開版本。1.0.1 的官方掃描與審核仍須重新上傳後確認。

## 服務測試與界線

Development checks on 2026-10-15 verified image responses for the 22-county/two-stage catalog. A separate PowerShell WebSession retrieved a georeferenced 1280×800 Taoyuan ministry-review image. Another HTTP-client comparison was rejected by the proxy with E1. Those historical checks are not repeated by the release builder and do not prove stable API rights.

The 30-minute renewal threshold is not proof of the server's natural token expiry. The earlier invalid-token exercise is not a natural-expiry test.

Linux, macOS, other QGIS versions, custom enterprise proxy/authentication settings, moving snapshots between computers and separate print-layout/atlas refreshes have not been separately validated.

QGIS's server-side security scan and final approval can only be confirmed after an actual upload. Local checks do not imply repository approval.
