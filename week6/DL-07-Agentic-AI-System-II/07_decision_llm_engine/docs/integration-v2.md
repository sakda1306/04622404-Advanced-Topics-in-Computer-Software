# Module 07 — contract v2 / release 0.2.0

> เอกสารประวัติรุ่น 0.2.0: การตั้งค่า policy และสถานะ upstream ในหน้านี้อาจเป็นข้อมูลเก่า ดู [integration-v3](integration-v3.md) สำหรับรุ่นปัจจุบัน 0.3.0 สูตร confidence ของ v2 ยังคงใช้โดยเพิ่ม quality flags ตาม v3

วันที่ 19 กันยายน 2026 ขอบเขตการแก้ไขเฉพาะ 07 ตามคำสั่งเจ้าของโมดูล:
confidence ผลลัพธ์เป็น float 0–1 และ 07 สร้าง Emergency Instructions
guide .txt ทั้งสามไฟล์ยังเป็นข้อกำหนดหลัก นโยบายยังเป็น prototype ไม่ใช่การรับรองใช้งานจริง

## Confidence
   
`DecisionResponse.confidence` เป็น JSON number ที่มีค่า finite ระหว่าง 0.0–1.0
`confidence_kind = heuristic_policy_score` หมายถึงคุณภาพหลักฐานสำหรับการตัดสิน action
ไม่ใช่โอกาสเกิดภัย ไม่ใช่ความมั่นใจที่ผ่าน calibration และไม่ใช่ risk score ของ 06

Input `risk.confidence` และ `quality.confidence` รับ JSON number 0–1 หรือ ordinal เดิม
เพื่อให้ request ของ 03/06 ยังเรียกได้; ไม่รับ boolean, numeric string, NaN หรือ Infinity
`risk.level` ยังคง LOW/MEDIUM/HIGH ไม่มี CRITICAL

เกณฑ์ต้นแบบใน `decision_engine/policies/prototype-v2.json`:

| รายการ | ค่า/ความหมาย |
|---|---|
| ordinal adapter | LOW = 0.25, MEDIUM = 0.65, HIGH = 0.90 |
| base | min(risk confidence, quality confidence); risk หาย = 0 |
| completeness | จำนวน risk/weather/transport/routes ที่มี หารด้วย 4 |
| freshness | จำนวน evidence ที่ fetched_at <= now < expires_at หารจำนวนทั้งหมด; ไม่มี = 0 |
| score | min(base × completeness × freshness, issue cap) |
| issue cap | ปกติ 1.0; มีปัญหา 0.25; conflicting 0.10 |
| escalation threshold | ต่ำกว่า 0.50; ไม่ปัดเศษก่อนเปรียบเทียบ |

ค่าการแปลง ordinal เป็นเกณฑ์ทดลองที่ระบุไว้อย่างชัดเจน ไม่ได้อ้างว่า HIGH เท่ากับความแม่นยำ 90%
ปัญหาคุณภาพใด ๆ ยังส่งตรวจต่อได้แม้ไม่ใช้ threshold เพียงอย่างเดียว
`confidence_details` แสดง base/completeness/freshness/issue_cap เพื่อคำนวณย้อนกลับ
การขาดคำแนะนำฉุกเฉินเพิ่ม escalation แยกต่างหาก ไม่ลดคะแนนความมั่นใจใน action ที่ล็อกแล้ว
เช่น มั่นใจว่าควรงดเดินทาง 0.9 แต่ยังไม่มีคำแนะนำเฉพาะพื้นที่

## Emergency Instructions

คืน object เมื่อ action = AVOID รวมทั้ง AVOID ที่เกิดจากข้อมูลไม่พอ
action อื่นคืน null + status not_required; ไม่ใช้ confidence สูงเป็นข้ออ้างลดประกาศปิดเส้นทาง

รูปแบบ object ตรง field ที่ 02 รองรับ:

```json
{
  "what_to_do_now": "ข้อความสิ่งที่ควรทำทันที",
  "safety_steps": ["ขั้นตอนจากข้อความที่ทบทวนไว้"],
  "contacts": [],
  "nearest_support": []
}
```

`emergency_assessment.status` = grounded / fallback / not_required
พร้อม procedure_id, evidence_ids, issues และ rejected_evidence เพื่อระบุสาเหตุที่ใช้ไม่ได้
citations รวมหลักฐานที่ใช้กับคำแนะนำ; evidence_status แยก used_by_decision/used_by_emergency
audit เก็บเฉพาะ IDs/status/version/digest ไม่เก็บเนื้อหาคำแนะนำ เบอร์โทร หรือพื้นที่

Input ใหม่ optional:

```json
{
  "emergency_context": {
    "context": {"request_id": "UUID เดียวกับ request", "route_id": "route เดียวกัน", "departure_time": "เวลาเดียวกันพร้อม timezone"},
    "region": "รหัสพื้นที่ที่ตกลงกับทีม",
    "hazard": "รหัสภัยที่ตกลงกับทีม"
  }
}
```

ตัวอย่างข้างบนเป็นคำอธิบาย field ไม่ใช่ payload พร้อมรัน ใช้ตัวอย่าง `examples/emergency_fallback.json` สำหรับทดสอบจริง
07 ไม่เดาพื้นที่/ชนิดภัยจาก free text หรือ route_id และไม่ดึงข้อมูลภายนอกเอง

### Catalog และการตรวจหลักฐาน

catalog เริ่มต้น `decision_engine/templates/emergency-v1.json` มี fallback ไทย/อังกฤษ
และ procedures ว่างโดยตั้งใจ: ยังไม่มีเอกสารคำแนะนำ/เบอร์ฉุกเฉินจริงที่ทบทวนร่วมกับทีม
ผลที่ใช้ได้ทันทีจึงเป็น fallback ที่บอกข้อจำกัดและขอให้ตรวจประกาศทางการ พร้อม escalation
ข้อความ fallback ไม่ยืนยันว่ามีเหตุฉุกเฉินเพียงเพราะ action = AVOID

ตั้ง `EMERGENCY_CATALOG_PATH` สำหรับไฟล์ที่ผู้ดูแลทบทวนแล้ว (อ่านครั้งเดียวตอนเริ่ม service)
หรือเพิ่มเวอร์ชัน catalog ใน package พร้อม review ของทีม ห้ามให้ผู้เรียก API ตั้ง path หรือส่งคำแนะนำมาแทน catalog
แต่ละ procedure ต้องมี:

- procedure_id, status = reviewed, region, hazard, locale ตรงกับ request
- source_url แบบ HTTPS ไม่มี credentials และ excerpt_sha256 ของเนื้อหาที่ทบทวน
- reviewed_at และ expires_at ที่ระบุ timezone และครอบคลุมเวลาประเมิน
- instructions ตาม object ข้างต้น; contacts ต้องทบทวนแหล่งที่มาในเอกสารเดียวกัน

เลือก procedure เมื่อพบ evidence kind=knowledge, official_source=true ที่ URL/hash ตรง
และยังไม่หมดอายุเท่านั้น ไม่เชื่อ official_source เพียง flag เดียว
ข้อความที่คืนมาจาก catalog ไม่ใช่ raw excerpt และไม่ส่ง excerpt ไป LLM
source URL/hash ไม่พิสูจน์ความแท้จริงผ่านเครือข่าย; upstream/ผู้ดูแลยังต้องยืนยันแหล่งข้อมูล
หาก facts conflicting หรือ warning ยังยืนยันไม่ได้ ใช้ fallback แม้พบ procedure
catalog ห้ามมี scope ซ้ำเพื่อไม่ให้เลือกคำแนะนำขัดแย้งกันโดยพลการ
nearest_support ว่างเสมอในรุ่นนี้ เพราะยังไม่มีข้อมูลตำแหน่งและการจัดอันดับระยะทาง
valid_until ไม่เกินอายุหลักฐานและอายุ review ที่ใช้ ต้องประเมินใหม่เมื่อหมดอายุ

ดูตัวอย่าง catalog จำลองครบ field ใน fixture `tests/test_confidence_emergency.py`
ข้อมูลนั้นใช้สำหรับทดสอบเท่านั้น ไม่ใช่คำแนะนำหรือเบอร์โทรจริง

## สิ่งที่เจ้าของโมดูลอื่นต้องทำต่อ (ยังไม่ได้แก้ให้)

| เจ้าของ | งานส่งต่อ |
|---|---|
| 03 | เพิ่มการรับ/ส่ง confidence และ emergency_instructions: ปัจจุบัน DecisionResult ยังไม่เก็บสอง field นี้และ response ยังตั้ง emergency_instructions=None |
| 03/06 | ตกลงรหัส region/hazard แล้วให้ 03 ส่ง emergency_context; knowledge excerpt ต้องตรงเนื้อหาที่ review รวมทั้ง metadata ที่ 06 ฝังใน excerpt ด้วย ไม่ parse metadata แบบเดา |
| 02/03/08 | ตกลงตำแหน่งและความหมายคะแนนก่อนใส่ใน risk.confidence เพราะคะแนนนี้ประเมิน action ไม่ใช่ calibration ของโมเดล risk |
| 08 | รับ confidence float; emergency_instructions ของ 08 ยังเป็น list ต่างจาก object ของ 02 ให้ map what_to_do_now + safety_steps และ contacts ไป official_contacts |
| ทีม | ยืนยันผู้ดูแลฐาน emergency contacts และเอกสารจริงสำหรับ catalog; auth/network และ root Compose เป็นงานรวม |

action mapping เดิมและระดับ risk ของ 07 ตรงกับ 02/06 แล้ว ไม่แก้ให้ตาม enum ที่ต่างของ 08
การเพิ่ม field ใน 07 ไม่ทำให้ UI รับ field ใหม่โดยอัตโนมัติ ต้องทำงานส่งต่อข้างต้นก่อน

## Version, Docker และ rollback

release 0.2.0, output schema 07-draft-v2, policy prototype-v2 พร้อม SHA256 และ catalog version/digest
quality.schema_version รับ v1/v2 เพื่อคง request เดิม; output เปลี่ยน confidence เป็น number อย่างชัดเจน
policy v1 เก็บเดิมไว้เพื่อประวัติ; release นี้ไม่รับการตั้งชื่อ v1 แล้วใช้สูตร v2
rollback ต้องย้อน release/code+policy+contract ให้สอดคล้องกัน ไม่ใช่เปลี่ยนชื่อ env อย่างเดียว

Docker ใช้ catalog ที่ bundle ภายใน image ได้เลย ไม่มี service เพิ่ม
เมื่อตั้ง custom catalog ใน container ต้อง mount ไฟล์ read-only และตั้ง path ภายใน container
Compose ใน 07 ไม่ได้แชร์ network กับ Compose ของทีมโดยอัตโนมัติ
LLM_TIMEOUT เริ่มต้นลดเหลือ 3 วินาทีเพื่อเหลือเวลา HTTP/audit ภายใน per-tool timeout ของ 03
ยังไม่มี live LLM provider และยังไม่ได้ทดสอบเวลาจริงกับบริการรวม
