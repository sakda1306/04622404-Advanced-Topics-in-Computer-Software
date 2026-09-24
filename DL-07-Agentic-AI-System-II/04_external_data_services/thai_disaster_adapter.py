"""Convert Thai Open Data Portal (data.go.th / DDPM / TMD) disaster events to Canonical records."""

from __future__ import annotations

import json
import math
import os
import re
import socket
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA = "canonical-record-v0.1-proposed"
CACHE_TTL = timedelta(minutes=30)
DEFAULT_TIMEOUT_SECONDS = 15

DATA_GO_TH_ENDPOINT = "https://data.go.th/api/3/action/datastore_search"
DPM_DEFAULT_RESOURCE_ID = "dpm-disaster-incidents"

THAI_PROVINCE_CENTROIDS: dict[str, tuple[float, float]] = {
    "กรุงเทพมหานคร": (100.5018, 13.7563),
    "กรุงเทพ": (100.5018, 13.7563),
    "bangkok": (100.5018, 13.7563),
    "เชียงใหม่": (98.9853, 18.7883),
    "chiang mai": (98.9853, 18.7883),
    "เชียงราย": (99.8325, 19.9072),
    "chiang rai": (99.8325, 19.9072),
    "ภูเก็ต": (98.3923, 7.8804),
    "phuket": (98.3923, 7.8804),
    "ชลบุรี": (100.9847, 13.3611),
    "chonburi": (100.9847, 13.3611),
    "สงขลา": (100.5954, 7.1897),
    "หาดใหญ่": (100.4747, 7.0087),
    "songkhla": (100.5954, 7.1897),
    "นครราชสีมา": (102.0978, 14.9799),
    "โคราช": (102.0978, 14.9799),
    "nakhon ratchasima": (102.0978, 14.9799),
    "ขอนแก่น": (102.8236, 16.4322),
    "khon kaen": (102.8236, 16.4322),
    "อุดรธานี": (102.7872, 17.4157),
    "udon thani": (102.7872, 17.4157),
    "อุบลราชธานี": (104.8594, 15.2287),
    "ubon ratchathani": (104.8594, 15.2287),
    "สุราษฎร์ธานี": (99.3215, 9.1382),
    "surat thani": (99.3215, 9.1382),
    "พระนครศรีอยุธยา": (100.5684, 14.3532),
    "อยุธยา": (100.5684, 14.3532),
    "ayutthaya": (100.5684, 14.3532),
    "นนทบุรี": (100.5217, 13.8591),
    "nonthaburi": (100.5217, 13.8591),
    "ปทุมธานี": (100.5250, 14.0208),
    "pathum thani": (100.5250, 14.0208),
    "สมุทรปราการ": (100.5998, 13.5991),
    "samut prakan": (100.5998, 13.5991),
    "กระบี่": (98.9063, 8.0863),
    "krabi": (98.9063, 8.0863),
    "พังงา": (98.5255, 8.4509),
    "phang nga": (98.5255, 8.4509),
    "ระนอง": (98.6348, 9.9658),
    "ranong": (98.6348, 9.9658),
    "ชุมพร": (99.1800, 10.4930),
    "chumphon": (99.1800, 10.4930),
    "นครศรีธรรมราช": (99.9631, 8.4325),
    "nakhon si thammarat": (99.9631, 8.4325),
    "ตรัง": (99.6114, 7.5563),
    "trang": (99.6114, 7.5563),
    "พัทลุง": (100.0740, 7.6167),
    "phatthalung": (100.0740, 7.6167),
    "สตูล": (100.0674, 6.6238),
    "satun": (100.0674, 6.6238),
    "ปัตตานี": (101.2501, 6.8696),
    "pattani": (101.2501, 6.8696),
    "ยะลา": (101.2804, 6.5411),
    "yala": (101.2804, 6.5411),
    "นราธิวาส": (101.8253, 6.4255),
    "narathiwat": (101.8253, 6.4255),
    "กาญจนบุรี": (99.5328, 14.0228),
    "kanchanaburi": (99.5328, 14.0228),
    "สุพรรณบุรี": (100.1177, 14.4745),
    "นครปฐม": (100.0601, 13.8196),
    "สมุทรสาคร": (100.2744, 13.5475),
    "สมุทรสงคราม": (100.0023, 13.4098),
    "เพชรบุรี": (99.9391, 13.1114),
    "หัวหิน": (99.9577, 12.5684),
    "ประจวบคีรีขันธ์": (99.7973, 11.8124),
    "ฉะเชิงเทรา": (101.0779, 13.6904),
    "ปราจีนบุรี": (101.3716, 14.0509),
    "สระแก้ว": (102.0718, 13.8140),
    "นครนายก": (101.2131, 14.2069),
    "ระยอง": (101.2816, 12.6814),
    "จันทบุรี": (102.1039, 12.6114),
    "ตราด": (102.5175, 12.2428),
    "สระบุรี": (100.9101, 14.5289),
    "ลพบุรี": (100.6534, 14.7995),
    "อ่างทอง": (100.4550, 14.5896),
    "สิงห์บุรี": (100.4015, 14.8936),
    "ชัยนาท": (100.1252, 15.1852),
    "อุทัยธานี": (100.0245, 15.3835),
    "นครสวรรค์": (100.1199, 15.6987),
    "พิจิตร": (100.3488, 16.4419),
    "พิษณุโลก": (100.2659, 16.8211),
    "สุโขทัย": (99.8234, 17.0078),
    "เพชรบูรณ์": (101.1567, 16.4190),
    "ตาก": (99.1258, 16.8839),
    "แม่สอด": (98.5694, 16.7167),
    "กำแพงเพชร": (99.5227, 16.4828),
    "ลำปาง": (99.4928, 18.2888),
    "ลำพูน": (99.0087, 18.5744),
    "แพร่": (100.1411, 18.1446),
    "น่าน": (100.7782, 18.7816),
    "พะเยา": (99.9022, 19.1664),
    "แม่ฮ่องสอน": (97.9654, 19.3021),
    "อุตรดิตถ์": (100.0993, 17.6201),
    "ชัยภูมิ": (102.0284, 15.8105),
    "บุรีรัมย์": (103.1029, 14.9930),
    "สุรินทร์": (103.4936, 14.8818),
    "ศรีสะเกษ": (104.3220, 15.1186),
    "มหาสารคาม": (103.3007, 16.1853),
    "ร้อยเอ็ด": (103.6520, 16.0538),
    "กาฬสินธุ์": (103.5063, 16.4327),
    "สกลนคร": (104.1486, 17.1664),
    "นครพนม": (104.7844, 17.3999),
    "มุกดาหาร": (104.7235, 16.5436),
    "ยโสธร": (104.1451, 15.7926),
    "อำนาจเจริญ": (104.6298, 15.8585),
    "หนองบัวลำภู": (102.4407, 17.2044),
    "เลย": (101.7223, 17.4860),
    "หนองคาย": (102.7420, 17.8783),
    "บึงกาฬ": (103.6531, 18.3619),
}

DISASTER_KEYWORD_TO_TYPE: list[tuple[str, str]] = [
    (r"(น้ำท่วม|อุทกภัย|น้ำป่า|น้ำล้นตลิ่ง|น้ำท่วมขัง|flood)", "FL"),
    (r"(ดินถล่ม|ดินโคลนถล่ม|ดินสไลด์|หินร่วง|landslide)", "LS"),
    (r"(วาตภัย|พายุ|ลมกระโชกแรง|ลมพายุ|storm|cyclone)", "ST"),
    (r"(ไฟป่า|จุดความร้อน|หมอกควัน|wildfire)", "WF"),
    (r"(แผ่นดินไหว|earthquake)", "EQ"),
    (r"(คลื่นลมแรง|สึนามิ|ภัยทางทะเล|tsunami)", "MA"),
    (r"(ภัยแล้ง|ฝนทิ้งช่วง|drought)", "DR"),
]

SEVERITY_MAPPINGS: list[tuple[str, str]] = [
    (r"(วิกฤต|สีแดง|รุนแรงมาก|ประกาศเขตภัยพิบัติ|อันตราย|อพยพ|red|critical|high)", "HIGH"),
    (r"(เฝ้าระวังพิเศษ|สีส้ม|เตือนภัย|ปานกลาง|orange|warning|medium)", "MEDIUM"),
    (r"(แจ้งเตือน|สีเหลือง|สีเขียว|เฝ้าระวัง|เบาบาง|yellow|green|advisory|low)", "LOW"),
]


class ThaiDisasterDataError(ValueError):
    """Thai Open Data / REST API returned an unusable response."""


def _aware_utc(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(cleaned, fmt)
                parsed = parsed.replace(tzinfo=timezone(timedelta(hours=7)))
                break
            except ValueError:
                continue
        else:
            return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=7)))
    return parsed.astimezone(timezone.utc).isoformat()


def _resolve_coordinates(
    item: dict,
) -> tuple[float, float] | None:
    for lon_key in ("longitude", "lon", "lng"):
        for lat_key in ("latitude", "lat"):
            lon_val = item.get(lon_key)
            lat_val = item.get(lat_key)
            if lon_val is not None and lat_val is not None:
                try:
                    lon, lat = float(lon_val), float(lat_val)
                    if math.isfinite(lon) and math.isfinite(lat):
                        if 97.0 <= lon <= 106.0 and 5.0 <= lat <= 21.0:
                            return lon, lat
                except (ValueError, TypeError):
                    pass

    text_to_search = " ".join(
        str(item.get(k) or "").lower()
        for k in ("province", "province_name", "province_th", "location", "name", "title", "description", "amphoe")
    )
    for prov_name, coords in THAI_PROVINCE_CENTROIDS.items():
        if prov_name.lower() in text_to_search:
            return coords

    return (100.5018, 13.7563)


def _classify_event_type(text: str) -> str:
    lower_text = text.lower()
    for pattern, code in DISASTER_KEYWORD_TO_TYPE:
        if re.search(pattern, lower_text):
            return code
    return "OT"


def _classify_severity(text: str) -> str:
    lower_text = text.lower()
    for pattern, severity in SEVERITY_MAPPINGS:
        if re.search(pattern, lower_text):
            return severity
    return "MEDIUM"


def to_canonical_disasters(
    payload: object, *, source_url: str, fetched_at: datetime
) -> list[dict]:
    """Convert Thai disaster records from Open Data or REST API into canonical schema."""
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must have a timezone")
    fetched_at = fetched_at.astimezone(timezone.utc)

    raw_items: list[dict] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("result"), dict) and isinstance(payload["result"].get("records"), list):
            raw_items = [r for r in payload["result"]["records"] if isinstance(r, dict)]
        elif isinstance(payload.get("data"), list):
            raw_items = [r for r in payload["data"] if isinstance(r, dict)]
        elif isinstance(payload.get("features"), list):
            for feat in payload["features"]:
                if isinstance(feat, dict) and isinstance(feat.get("properties"), dict):
                    props = dict(feat["properties"])
                    geom = feat.get("geometry")
                    if isinstance(geom, dict) and geom.get("type") == "Point" and isinstance(geom.get("coordinates"), list):
                        coords = geom["coordinates"]
                        if len(coords) >= 2:
                            props["longitude"], props["latitude"] = coords[0], coords[1]
                    raw_items.append(props)
        elif isinstance(payload.get("records"), list):
            raw_items = [r for r in payload["records"] if isinstance(r, dict)]
        elif isinstance(payload.get("items"), list):
            raw_items = [r for r in payload["items"] if isinstance(r, dict)]
    elif isinstance(payload, list):
        raw_items = [r for r in payload if isinstance(r, dict)]
    else:
        raise ThaiDisasterDataError("Thai disaster payload format is not recognized")

    records: list[dict] = []
    seen_ids: set[str] = set()

    for idx, item in enumerate(raw_items):
        raw_id = (
            item.get("incident_id")
            or item.get("id")
            or item.get("_id")
            or item.get("event_id")
            or item.get("code")
            or f"event-{idx + 1}"
        )
        record_id = f"thai_disaster:dpm:{raw_id}"
        if record_id in seen_ids:
            continue
        seen_ids.add(record_id)

        title = str(
            item.get("title")
            or item.get("name")
            or item.get("disaster_type")
            or item.get("incident_name")
            or "สถานการณ์สาธารณภัยในประเทศไทย"
        ).strip()

        desc = str(
            item.get("description")
            or item.get("detail")
            or item.get("situation")
            or title
        ).strip()

        combined_text = f"{title} {desc}"
        event_type = _classify_event_type(combined_text)

        severity_raw = str(
            item.get("severity")
            or item.get("severity_level")
            or item.get("alert_level")
            or item.get("level")
            or ""
        )
        severity = _classify_severity(f"{severity_raw} {combined_text}")

        coords = _resolve_coordinates(item)
        footprint = {"type": "Point", "coordinates": [coords[0], coords[1]]} if coords else None

        starts_at = _aware_utc(item.get("start_date") or item.get("starts_at") or item.get("date"))
        ends_at = _aware_utc(item.get("end_date") or item.get("ends_at"))
        event_time = starts_at or fetched_at.isoformat()

        province = str(
            item.get("province")
            or item.get("province_name")
            or item.get("province_th")
            or ""
        ).strip()

        flags = []
        if not starts_at:
            flags.append("approximate_time")
        if not coords:
            flags.append("approximate_location")

        records.append(
            {
                "schema_version": SCHEMA,
                "record_id": record_id,
                "record_kind": "disaster_event",
                "status": "available",
                "source": {
                    "name": "Department of Disaster Prevention and Mitigation (DDPM) / Open Government Data",
                    "authority": "DDPM Thailand",
                },
                "source_lineage": source_url,
                "spatial_footprint": footprint,
                "observed_at": None,
                "valid_at": None,
                "issued_at": starts_at,
                "event_time": event_time,
                "fetched_at": fetched_at.isoformat(),
                "expires_at": (fetched_at + CACHE_TTL).isoformat(),
                "severity": severity,
                "quality_flags": flags,
                "value": {
                    "event_type": event_type,
                    "name": title,
                    "alert_level": severity_raw or severity,
                    "country": "Thailand",
                    "province": province,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "description": desc[:2000],
                },
            }
        )

    return records


def _unavailable(fetched_at: datetime, code: str, source_url: str) -> dict:
    return {
        "schema_version": SCHEMA,
        "record_id": f"thai_disaster:check:{fetched_at.timestamp():.0f}",
        "record_kind": "disaster_event",
        "status": "unavailable",
        "source": {
            "name": "Department of Disaster Prevention and Mitigation (DDPM) / Open Government Data",
            "authority": "DDPM Thailand",
        },
        "source_lineage": source_url,
        "spatial_footprint": None,
        "observed_at": None,
        "valid_at": None,
        "issued_at": None,
        "event_time": None,
        "fetched_at": fetched_at.isoformat(),
        "expires_at": None,
        "severity": None,
        "quality_flags": ["unavailable"],
        "value": None,
        "error_code": code,
    }


def _mock_thai_disasters(now: datetime) -> list[dict]:
    sample_payload = {
        "success": True,
        "result": {
            "records": [
                {
                    "incident_id": "DPM-67-0891",
                    "title": "สถานการณ์น้ำป่าไหลหลากและดินถล่มริมทางหลวง",
                    "province": "เชียงราย",
                    "amphoe": "แม่สาย",
                    "severity_level": "วิกฤต",
                    "latitude": 20.4331,
                    "longitude": 99.8824,
                    "start_date": (now - timedelta(hours=6)).isoformat(),
                    "situation": "น้ำป่าไหลหลากล้นตลิ่ง เข้าท่วมผิวจราจรเส้นทางริมแม่น้ำสาย",
                },
                {
                    "incident_id": "TMD-2026-ST04",
                    "title": "ประกาศเตือนภัยพายุดีเปรสชันและคลื่นลมแรงในอ่าวไทย",
                    "province": "สงขลา",
                    "amphoe": "เมือง",
                    "severity_level": "เตือนภัย",
                    "latitude": 7.1897,
                    "longitude": 100.5954,
                    "start_date": (now - timedelta(hours=3)).isoformat(),
                    "situation": "มีฝนตกหนักถึงหนักมากและมีคลื่นลมแรง คลื่นสูง 2-3 เมตร",
                },
            ]
        },
    }
    return to_canonical_disasters(
        sample_payload,
        source_url="https://data.go.th/api/3/action/datastore_search?resource_id=mock-dpm-events",
        fetched_at=now,
    )


def fetch_canonical_disasters(
    *,
    now: datetime | None = None,
    api_key: str | None = None,
    endpoint: str | None = None,
    resource_id: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict]:
    """Fetch recent Thai disaster incidents from data.go.th or REST endpoint."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must have a timezone")
    now = now.astimezone(timezone.utc)

    mock_enabled = os.getenv("THAI_DISASTER_MOCK_FALLBACK", "false").lower() in ("true", "1", "yes")
    if mock_enabled:
        return _mock_thai_disasters(now)

    key = api_key if api_key is not None else os.getenv("DATA_GO_TH_API_KEY", os.getenv("DISASTER_API_KEY", ""))
    target_url = endpoint or os.getenv("THAI_DISASTER_API_URL")
    custom_resource_id = resource_id or os.getenv("DATA_GO_TH_DISASTER_RESOURCE_ID")

    if not target_url and not custom_resource_id and not key:
        return [_unavailable(now, "PROVIDER_NOT_CONFIGURED", DATA_GO_TH_ENDPOINT)]

    if not target_url:
        rid = custom_resource_id or DPM_DEFAULT_RESOURCE_ID
        params = urlencode({"resource_id": rid, "limit": 100})
        target_url = f"{DATA_GO_TH_ENDPOINT}?{params}"

    headers = {
        "User-Agent": "Team-D-travel-safety-platform/1.0",
        "Accept": "application/json",
    }
    if key:
        headers["api-key"] = key

    request = Request(target_url, headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
    except HTTPError as error:
        code = "PROVIDER_AUTH_FAILED" if error.code in (401, 403) else "PROVIDER_HTTP_ERROR"
        return [_unavailable(now, code, target_url)]
    except (URLError, TimeoutError, socket.timeout):
        return [_unavailable(now, "PROVIDER_UNAVAILABLE", target_url)]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return [_unavailable(now, "PROVIDER_DATA_INVALID", target_url)]

    try:
        return to_canonical_disasters(payload, source_url=target_url, fetched_at=now)
    except ThaiDisasterDataError:
        return [_unavailable(now, "PROVIDER_DATA_INVALID", target_url)]
