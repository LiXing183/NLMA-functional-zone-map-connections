import json
import math
import re
from urllib.parse import urlencode

TITLE = 'NLMA國土功能分區圖連線'
LAYER_NAME = 'NLMA_國土功能分區'
SERVICE = 'https://nluz.nlma.gov.tw/nluzmap/rest/services/Exhibition/Exhibition_NLU_/MapServer'
PROXY = 'https://nluz.nlma.gov.tw/ex3smap/mapproxy?'
TOKEN_MAX_AGE = 30 * 60
PROPERTY = 'nluz_background/'
IMAGE_PROPERTIES = ('image_state', 'image_county', 'image_version', 'image_crs',
                    'image_bbox', 'image_size', 'image_updated_at')


def version_label(version):
    return {'報部版': '報部審議階段', '公展版': '公開展覽階段'}.get(version, version)


def displayed_image(layer):
    state = layer.customProperty(PROPERTY + 'image_state', 'legacy')
    if state == 'empty':
        return '尚無成功影像'
    if state == 'uncertain':
        return '影像還原未完成，請重新連線'
    county = layer.customProperty(PROPERTY + 'image_county', '')
    version = layer.customProperty(PROPERTY + 'image_version', '')
    if state != 'ready' or not county or not version:
        return '舊版保留影像（縣市與版本尚未驗證）'
    return '%s／%s' % (county, version_label(version))


def county_epsg(county):
    return 3825 if county in ('澎湖縣', '金門縣', '連江縣') else 3826


def announcement_text(announcements, county, version):
    section = 'report_counties' if version == '報部版' else 'counties'
    row = announcements.get(section, {}).get(county)
    if not row:
        return '尚未取得此縣市／版本的公告。'
    heading = '報部審議階段' if version == '報部版' else '公開展覽階段'
    return heading + '\n' + row['title']


def entry_url(county, version):
    return 'https://nluz.nlma.gov.tw/ex3smap/default.aspx?' + urlencode({'CN': county, 'version': version})


def parse_entry(data, county, version):
    text = data.decode('utf-8-sig')
    tokens = re.findall(r'''\bconst\s+layerToken\s*=\s*["']([A-Za-z0-9_.~+/-]{16,2048}={0,2})["']''', text)
    match = re.search(r'\bconst\s+m_lyrcode\s*=\s*(\[[^;]*\])\s*;', text)
    if len(set(tokens)) != 1 or not match:
        raise ValueError('官方入口未提供有效 Token／圖層設定；可能需要驗證或網站已變更')
    rows = json.loads(match[1])
    selected = [r for r in rows if r.get('name') == county and r.get('version') == version]
    if len(selected) != 1 or not isinstance(selected[0].get('id'), int) or selected[0]['id'] < 0:
        raise ValueError('官方頁面尚未提供此縣市／版本的可用圖層')
    return tokens[0], selected[0]['id']


def network_error(code):
    code = int(getattr(code, 'value', code))
    if not code:
        return None
    return {
        1: '伺服器拒絕連線', 2: '連線中斷，回應未完整接收',
        3: '找不到服務主機，請檢查網路或 DNS', 4: '網路連線逾時',
        5: '請求已取消', 6: '安全連線憑證驗證失敗（TLS）',
        7: '網路暫時中斷', 8: '網路工作階段失敗',
        101: '代理伺服器拒絕連線', 102: '代理伺服器連線中斷',
        103: '找不到代理伺服器', 104: '代理伺服器連線逾時',
        105: '代理伺服器需要驗證',
    }.get(code, '網路請求失敗（代碼 %s）' % code)


def response_error(status, data, network_code=0, allow_html=False):
    if status in (401, 403, 498, 499):
        return '授權／工作階段錯誤（HTTP %s）' % status
    try:
        info = json.loads(data)
    except (ValueError, UnicodeError):
        info = None
    if isinstance(info, dict) and 'error' in info:
        err = info['error']
        code = err.get('code') if isinstance(err, dict) else None
        if code in (401, 403, 498, 499):
            return 'Token 失效、已到期或權限不足（服務代碼 %s）' % code
        return '服務回傳錯誤，未取得有效影像'
    transport = network_error(network_code)
    if transport and (status is None or status == 200 or int(getattr(network_code, 'value', network_code)) < 200):
        return transport
    if status != 200:
        return '尚未收到 HTTP 回應，請檢查網路連線' if status is None else '請求失敗（HTTP %s）' % status
    if allow_html:
        return None
    text = data[:4096].decode('utf-8', errors='ignore').strip()
    if text in ('E1', 'E2'):
        return '官方代理拒絕請求（%s）' % text
    if text.startswith('<') or 'top.location' in text:
        return '收到 HTML／重新導向內容，可能需要重新驗證'
    return None


def square_geometry(bounds, pixels):
    xmin, ymin, xmax, ymax = bounds
    if not all(math.isfinite(v) for v in bounds):
        raise ValueError('Invalid bounds')
    side = max(xmax - xmin, ymax - ymin)
    if side <= 0 or side > 40075016.7:
        raise ValueError('Unsupported extent')
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    return (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2), side / pixels


def token_due(acquired, now):
    return acquired is None or now - acquired >= TOKEN_MAX_AGE


def render_size(width, height, device_ratio, limit):
    # At least 2x sampling helps the final QGIS reprojection. Match DPI to the
    # actual sampling ratio so labels do not shrink when pixels increase.
    logical = max(1, width, height)
    ratio = max(2.0, float(device_ratio))
    pixels = max(512, min(limit, int(math.ceil(logical * ratio))))
    dpi = max(1, int(round(96 * pixels / logical)))
    return pixels, dpi


def render_geometry(bounds, pixels):
    """Use square ground pixels, padding at most one pixel per dimension.

    ArcGIS adjusts a bbox whose ratio differs from size. Explicitly pad bounds
    to the exact integer image ratio so the world file describes the response.
    """
    xmin, ymin, xmax, ymax = bounds
    width, height = xmax - xmin, ymax - ymin
    if not all(math.isfinite(v) for v in bounds) or min(width, height) <= 0:
        raise ValueError('Invalid bounds')
    side = max(width, height)
    if side > 40075016.7 or pixels < 1:
        raise ValueError('Unsupported extent')
    resolution = side / pixels
    cols = min(pixels, max(1, math.ceil(width / resolution)))
    rows = min(pixels, max(1, math.ceil(height / resolution)))
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    half_width, half_height = cols * resolution / 2, rows * resolution / 2
    return (cx - half_width, cy - half_height, cx + half_width, cy + half_height), (cols, rows), resolution
