# 驗證紀錄 / Validation

## 實機回報

發布準備時，維護者在對話中確認「測試功能已正常運作」，並確認測試版本為 **QGIS 4.2.3**。操作環境為 Windows。

This is a maintainer/user report, not an automated QGIS runtime result. No detailed new per-scenario test record was supplied. The 1.0.0 publication package keeps the runtime Python files from the confirmed 0.2.2 build unchanged.

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

For version 1.0.0, the 12 offline regression groups and package checks passed. The five runtime Python files, icon and three map configuration files were compared byte-for-byte against the local 0.2.2 installation ZIP.

- Bandit 1.9.4: no findings and no scan errors in the plugin source.
- detect-secrets 1.5.0: no candidates in the plugin directory, using `--all-files --no-verify` (no network verification of potential secrets).
- Flake8 7.4.1: 84 findings — 78 long lines (E501), four continuation-indentation issues (E127/E128), one ambiguous short variable (E741) and one unused import (F401). No undefined-name or syntax diagnostics were reported. These findings remain; the already-tested runtime code was not reformatted for publication.

These local tools do not prove the absence of defects or replace the upload-time scan. [QGIS's scanner documentation](https://plugins.qgis.org/docs/security-scanning/tools) describes Flake8 findings as informational. The machine-readable local result is in [local_checks.json](local_checks.json).

## 服務測試與界線

Development checks on 2026-10-15 verified image responses for the 22-county/two-stage catalog. A separate PowerShell WebSession retrieved a georeferenced 1280×800 Taoyuan ministry-review image. Another HTTP-client comparison was rejected by the proxy with E1. Those historical checks are not repeated by the release builder and do not prove stable API rights.

The 30-minute renewal threshold is not proof of the server's natural token expiry. The earlier invalid-token exercise is not a natural-expiry test.

Linux, macOS, other QGIS versions, custom enterprise proxy/authentication settings, moving snapshots between computers and separate print-layout/atlas refreshes have not been separately validated.

QGIS's server-side security scan and final approval can only be confirmed after an actual upload. Local checks do not imply repository approval.
