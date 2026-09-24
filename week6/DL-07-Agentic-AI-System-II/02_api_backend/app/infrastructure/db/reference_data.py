"""Reference data: service coverage and default emergency instructions.

Both datasets are placeholders until their owners provide official data
(docs/02_api_spec.md open question 4; docs/03_data_design.md section 3.13).
Seeding is idempotent: rows are inserted or updated by primary key.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import CoverageAreaModel, EmergencyDefaultModel

# Rough bounding polygon around Thailand (lon/lat). It also covers border areas of
# neighbouring countries; replace it with the official boundary before production.
THAILAND_BOUNDS_WKT = "MULTIPOLYGON(((97.3 5.6, 105.7 5.6, 105.7 20.5, 97.3 20.5, 97.3 5.6)))"

COVERAGE_AREAS: list[dict[str, Any]] = [
    {
        "code": "TH",
        "name": "Thailand",
        "wkt": THAILAND_BOUNDS_WKT,
        "source": "placeholder bounding polygon, pending official boundary data",
    },
]

_TH_CONTACTS = [
    {"name": "Police", "phone": "191", "available_hours": "24/7"},
    {"name": "Emergency Medical Services", "phone": "1669", "available_hours": "24/7"},
    {"name": "Fire and Rescue", "phone": "199", "available_hours": "24/7"},
    {"name": "Tourist Police", "phone": "1155", "available_hours": "24/7"},
    {
        "name": "Department of Disaster Prevention and Mitigation",
        "phone": "1784",
        "available_hours": "24/7",
    },
]

EMERGENCY_DEFAULTS: list[dict[str, Any]] = [
    {
        "region_code": "TH",
        "language": "en",
        "instructions": {
            "what_to_do_now": (
                "Stop travelling toward the affected area and move to a safe place. "
                "Follow instructions from local authorities."
            ),
            "safety_steps": [
                "Stay away from flood water, fallen power lines and damaged roads.",
                "Keep your phone charged and share your location with someone you trust.",
                "Check official announcements before continuing your trip.",
            ],
            "contacts": _TH_CONTACTS,
            "nearest_support": [],
        },
    },
    {
        "region_code": "TH",
        "language": "th",
        "instructions": {
            "what_to_do_now": (
                "หยุดการเดินทางเข้าพื้นที่เสี่ยงและไปยังที่ปลอดภัย ปฏิบัติตามคำแนะนำของเจ้าหน้าที่ในพื้นที่"
            ),
            "safety_steps": [
                "หลีกเลี่ยงน้ำท่วม สายไฟที่ขาด และถนนที่เสียหาย",
                "ชาร์จโทรศัพท์ให้พร้อมและแชร์ตำแหน่งให้คนที่ไว้ใจ",
                "ตรวจสอบประกาศจากหน่วยงานทางการก่อนเดินทางต่อ",
            ],
            "contacts": [
                {"name": "ตำรวจ", "phone": "191", "available_hours": "24 ชั่วโมง"},
                {"name": "เจ็บป่วยฉุกเฉิน", "phone": "1669", "available_hours": "24 ชั่วโมง"},
                {"name": "ดับเพลิงและกู้ภัย", "phone": "199", "available_hours": "24 ชั่วโมง"},
                {"name": "ตำรวจท่องเที่ยว", "phone": "1155", "available_hours": "24 ชั่วโมง"},
                {
                    "name": "กรมป้องกันและบรรเทาสาธารณภัย",
                    "phone": "1784",
                    "available_hours": "24 ชั่วโมง",
                },
            ],
            "nearest_support": [],
        },
    },
]

EMERGENCY_SOURCE = "public national hotlines, pending review by the data owner"


async def seed_reference_data(session: AsyncSession) -> dict[str, int]:
    for area in COVERAGE_AREAS:
        values = {
            "code": area["code"],
            "name": area["name"],
            "area": func.ST_GeogFromText(f"SRID=4326;{area['wkt']}"),
            "source": area["source"],
        }
        stmt = insert(CoverageAreaModel).values(**values)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[CoverageAreaModel.code],
                set_={
                    "name": stmt.excluded.name,
                    "area": stmt.excluded.area,
                    "source": stmt.excluded.source,
                    "updated_at": func.now(),
                },
            )
        )

    for item in EMERGENCY_DEFAULTS:
        stmt = insert(EmergencyDefaultModel).values(
            region_code=item["region_code"],
            language=item["language"],
            instructions=item["instructions"],
            source=EMERGENCY_SOURCE,
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[EmergencyDefaultModel.region_code, EmergencyDefaultModel.language],
                set_={
                    "instructions": stmt.excluded.instructions,
                    "source": stmt.excluded.source,
                    "updated_at": func.now(),
                },
            )
        )

    return {"coverage_areas": len(COVERAGE_AREAS), "emergency_defaults": len(EMERGENCY_DEFAULTS)}
