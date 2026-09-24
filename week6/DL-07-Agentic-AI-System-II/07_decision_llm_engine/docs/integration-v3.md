# Module 07 — integration draft v3 / release 0.3.0

เอกสารนี้ต่อจาก integration-v2 และเป็นฉบับปัจจุบันของ 07 เท่านั้น ยังไม่ใช่ contract ที่ทุกทีมตกลงแล้ว การเปลี่ยนแปลงทั้งหมดอยู่ในโฟลเดอร์ 07

## Data quality และ confidence

รับ flags เดิม `missing`, `stale`, `conflicting`, `incomplete`, `inferred` และเพิ่ม:

| Flag จากต้นทาง | ผลใน policy prototype-v3 |
|---|---|
| `partial` | เก็บ flag เดิมและเพิ่มเหตุผล `incomplete`; งดเลือกทาง/เวลาที่ดูปลอดภัยขึ้นจากข้อมูลไม่ครบ |
| `freshness_unknown` | เก็บ flag เดิมและเพิ่ม `freshness_requires_review`; ไม่ถือ timestamp ที่ส่งมาว่ายืนยันความสดได้แล้ว |

ทั้งสองกรณีจำกัด confidence ไม่เกิน 0.25 และส่ง escalation แม้ risk เป็น LOW หรือมีทางเลือก ส่วน `conflicting` จำกัดไม่เกิน 0.1 เช่นเดิม กฎประกาศทางการและ HIGH ยังมีลำดับสูงกว่า กรณี fallback AVOID จากข้อมูลไม่พอไม่ได้ยืนยันว่ามีภัยจริง

`confidence` ผลลัพธ์ยังเป็น float 0–1 เป็นคะแนน heuristic ของนโยบาย ไม่ใช่โอกาสเกิดภัย ส่วน `risk.level` ยังคง HIGH/MEDIUM/LOW ตาม contract ความเสี่ยง รองรับ ordinal confidence input จาก 03/06 เพื่อเปลี่ยนผ่าน

ตัวอย่าง `summary_only_risk` จำลอง risk MEDIUM/confidence LOW ที่ adapter อาจส่งจากผลสรุปของ 06 ไม่ใช่ response ดิบของ 06 และไม่ได้สร้างหลักฐานจริงให้ผลสรุป ตัวอย่าง `partial_alternative` ไม่ตั้ง clearly_safer เมื่อ coverage ไม่ครบ การทดสอบเหล่านี้ทดสอบขอบเขต 07 ยังไม่ใช่การเรียก 06 จริง

ใช้ `DECISION_POLICY_VERSION=prototype-v3` และถ้าตั้ง `ESCALATION_RULES` ไว้เองต้องเพิ่ม `partial,freshness_unknown` ตาม `.env.example` โค้ดรุ่นนี้ปฏิเสธ policy v1/v2 เพื่อไม่ให้ระบุเวอร์ชันเก่าบนพฤติกรรมใหม่ เก็บ manifests เดิมโดยไม่แก้ไข; rollback ต้องใช้ code/config/lock ของรุ่นเดิมร่วมกัน

Input `quality.schema_version` ยังรับ v1/v2 และเพิ่ม `07-draft-v3`; response ประกาศ v3

## Emergency contact metadata ที่เสนอให้ทีม

คง `emergency_instructions` เป็น object ที่เข้ารูปแบบ strict ของ 02:
`what_to_do_now`, `safety_steps`, `contacts`, `nearest_support` และ contact ยังมีเพียง `name`, `phone`, `url`, `available_hours`

เพิ่ม field ระดับบนของ response `emergency_contact_metadata` เป็น dictionary ใช้ index ของ contact ในรูป string (`"0"`, `"1"`, ...) เป็น key ไม่ใส่ metadata ลงใน object ของ 02 ตัวอย่างโครงสร้าง metadata (ใช้ placeholder แสดงชื่อ field เท่านั้น):

```text
emergency_contact_metadata["0"] = {
  contact_type, region, effective_date, expires_at,
  directory_version, source_url
}
```

ข้อมูลต้องมาจาก reviewed local catalog: ภายใน catalog ใส่ object นี้ที่ `instructions.contacts[i].metadata`; service จะแยกออกเป็น field ระดับบนตอน serialize

- วันที่ต้องมี timezone และ effective_date < expires_at
- region และ source_url ต้องตรงกับ reviewed procedure; เอกสารนี้ยังไม่รองรับเบอร์ที่อ้างแหล่งอื่นแยกจาก procedure
- ใช้ contact เมื่อ effective_date <= now < expires_at และรูปแบบ phone ผ่านเท่านั้น
- หาก metadata หมดอายุหรือ phone ไม่ผ่าน จะงดส่ง contact และเพิ่ม escalation; guidance ที่ยังยืนยันได้คงอยู่
- valid_until ถูกจำกัดด้วยวันหมดอายุของ contact ที่ส่งออกด้วย
- ยังอ่าน catalog เก่าที่ไม่มี metadata ได้ แต่ตัวช่วยส่งต่อ 08 จะงดส่ง contact นั้นจนมี metadata ที่ทบทวนแล้ว
- ไม่มีการอนุมานพื้นที่ วันที่มีผล หมายเลข หรือ directory version และไม่ได้ตรวจแหล่งจริงผ่าน network
- ค่า directory_version เป็น provenance เท่านั้น ยังไม่ได้บังคับให้ตรงกับค่าตั้งของ 08 ต้องตกลงร่วมกันก่อน

Catalog ที่แจกยังไม่มีคำแนะนำเฉพาะภัยหรือหมายเลขใช้งานจริง การทดสอบทั้งหมดใช้ข้อมูลสังเคราะห์; `nearest_support` ยังว่างเพราะไม่มีข้อมูลตำแหน่งที่ยืนยันได้

## ตัวช่วยแปลงเฉพาะส่วน emergency สำหรับ 08

```python
from datetime import UTC, datetime
from decision_engine.handoff import emergency_fragment
from decision_engine.models import DecisionResponse

decision = DecisionResponse.model_validate(response_json)
fragment = emergency_fragment(decision, traveler_region=verified_region, now=datetime.now(UTC))
```

ผลลัพธ์มี `emergency_instructions` เป็น list[str], `official_contacts` ตามชื่อ field ของ 08, `contact_provenance` เพื่อไม่ทำข้อมูลแหล่ง/version/expiry หาย และ `limitations` ต้องให้ผู้ต่อระบบเก็บข้อมูลเหล่านี้ รวมถึง original decision/citations/escalation/valid_until ไว้

ตัวช่วยนี้ไม่ใช่ RecommendationResponse ทั้งชุด ไม่ใช่ endpoint ใหม่ และไม่ได้ต่อเข้าระบบของ 08 อัตโนมัติ ผู้เรียกต้องส่งพื้นที่ที่ยืนยันแล้ว หากส่งพื้นที่ว่าง/ไม่ตรง contact จะถูกงดส่ง กรณี decision หมดอายุหรือยังไม่ถึงเวลาประเมินจะยก ValueError ให้ขอผลใหม่

## ส่งต่อให้เจ้าของโมดูลอื่น

| เจ้าของ | สิ่งที่ยังต้องทำร่วมกัน |
|---|---|
| 03 | ส่ง quality flags และ emergency object ได้แล้ว และต่อ 05/06 จริงแล้ว; ยังต้องตกลงผู้ผลิต quality confidence/active_restriction, ส่ง emergency_context จาก region ที่ยืนยันแล้ว และตกลงว่าจะส่ง policy confidence ไปปลายทางอย่างไร |
| 05/06/03 | 05 ส่ง `covered` ได้และ 06 รับผลพร้อมประเมิน LOW/HIGH ได้แล้ว; ยังต้องยืนยัน semantics ของ quality confidence/active restriction และต่อ weather/route candidates จริงโดยไม่เติมหลักฐานหรือค่าความปลอดภัยเอง |
| 08 | ต่อ 07 โดยตรงได้แล้ว; หากใช้งานเส้นทางนี้ต้องเก็บ limitations/provenance/expiry และยืนยัน region/directory policy ส่วน D-12 ล่าสุดกำหนดว่า 02 ไม่เรียก 08 |
| ทีม | reviewed emergency sources, policy approval, service authentication และ Compose network ร่วม |

รอบนี้อ่าน schema ของเพื่อนเพื่อตรวจความเข้ากันได้เท่านั้น ไม่แก้ไฟล์ของเพื่อนและไม่อ้างว่าระบบรวมทำงานครบแล้ว

## ผลตรวจ contract หลังอัปเดต 21 กันยายน 2026

ชุดทดสอบของ 07 เรียก implementation จริงของ 05/06 และ `build_decision_request` ของ 03 ด้วยข้อมูล canonical สังเคราะห์ที่ควบคุมเวลา/พื้นที่ได้ ผลที่ต้องรักษาไว้คือ:

| ผลต้นทาง | ผลของ 07 |
|---|---|
| coverage ครบ, risk LOW แต่ quality confidence/active restriction ยังไม่ยืนยัน | AVOID, escalation มี `low_confidence` และ `restriction_unknown` |
| coverage ครบ, risk LOW, quality HIGH, active_restriction=false | NORMAL, confidence 0.9, ไม่ escalation |
| 06 ให้ risk HIGH | AVOID ด้วย `HIGH_RISK` และไม่ถูกลดระดับ |
| coverage ขาดบางหมวด | AVOID; ไม่เลือก route จากข้อมูล partial |

นี่เป็น contract integration test ใน process เดียว ไม่ใช่ live-provider/end-to-end test ทุก service และไม่ได้เปลี่ยนกฎให้ demo แสดง NORMAL เมื่อข้อมูลยังไม่ยืนยัน

## ทดสอบซ้ำ

```powershell
uv run pytest
uv run ruff check .
docker compose -p teamd-07 up --build -d --wait
uv run python scripts/smoke_http.py
```

Smoke ใช้เวลาปัจจุบันกับข้อมูลจำลอง 14 กรณี ตรวจ health/ready/OpenAPI และ 422 สำหรับ input ผิด โดยไม่เปลี่ยน timestamp ของข้อมูลจริง ตรวจสถานะผลที่รันล่าสุดใน implementation-status.md
