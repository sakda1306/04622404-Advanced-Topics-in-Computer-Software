# สรุปการพัฒนา Module 06: Risk and Knowledge Services

## ขอบเขตความรับผิดชอบ

Module 06 ทำหน้าที่สร้างหลักฐานเพื่อส่งให้ระบบตัดสินใจ โดยรับข้อมูลที่ผ่านการรวม
และตรวจคุณภาพจาก Module 05 แล้วประมวลผลเป็น 3 ส่วนหลัก:

1. การประเมินความเสี่ยงของการเดินทาง
2. การค้นคืนคำแนะนำเกี่ยวกับภัยพิบัติจากเอกสารที่ตรวจสอบแล้ว
3. การวิเคราะห์เส้นทางหลักและเส้นทางสำรอง

งานนี้ไม่ได้แก้ไข source code ของ Module 03, 05, 07 หรือโมดูลอื่น โดยอ่าน contract
ของโมดูลเหล่านั้นเพื่อใช้ตรวจสอบความเข้ากันได้เท่านั้น

## สิ่งที่พัฒนา

### 1. Risk assessment

- เพิ่ม deterministic baseline สำหรับประเมินข้อมูลอากาศ ภัยพิบัติ การขนส่ง
  และประกาศจำกัดการเดินทาง
- รองรับระดับความเสี่ยง `LOW`, `MEDIUM` และ `HIGH`
- ส่งคืน normalized risk score, ordinal confidence, model version และ reason factors
- ใช้ active official closure หรือข้อจำกัดทางการเป็น hard safety override ระดับ `HIGH`
- ใช้ผลลัพธ์แบบ conservative `HIGH` และ confidence `LOW` เมื่อไม่มี
  `IntegratedTravelContext`
- ใช้ผลลัพธ์แบบ conservative `MEDIUM`, score ไม่ทราบค่า และ confidence `LOW`
  เมื่อได้รับเพียง summary context ที่ไม่มีหลักฐานรายละเอียด แม้ระบุว่าไม่มีข้อจำกัดก็ตาม
- รองรับ quality flags `partial`, `freshness_unknown` และ `uncertain` จาก Module 05
- ปฏิเสธ feature schema version ที่ระบบยังไม่รองรับ
- ระบุชัดเจนว่าคะแนนจาก baseline ยังไม่ใช่ calibrated probability

### 2. Disaster knowledge retrieval

- รับ hazard จาก active official alerts เพื่อสร้าง retrieval query
- กรองเอกสารตามสถานะอนุมัติ หน่วยงาน ภาษา พื้นที่ ประเภทภัย วันที่เริ่มใช้
  และวันหมดอายุ
- ใช้ BM25-style lexical retrieval ร่วมกับ hazard และ authority reranking
- ส่งคืน source URL, document ID, page, section, validity และ retrieval score
- คืนรายการว่างเมื่อไม่พบหลักฐานที่เพียงพอ โดยไม่สร้างคำแนะนำฉุกเฉินขึ้นเอง
- ยังไม่บรรจุ safety corpus จริง เนื่องจากเอกสารต้องผ่านการตรวจและอนุมัติจากทีมก่อน

### 3. Route analysis

- รองรับ GeoJSON `LineString` และ timed route segments จาก Module 05
- คำนวณระยะทางของเส้นทางและระยะเวลาเดินทาง
- ประเมินหลักฐานที่จับคู่กับแต่ละช่วงของเส้นทาง
- ใช้ official closure และคำสั่ง `AVOID` เป็น hard constraints
- ระบุว่าเส้นทางหลักใช้งานได้หรือไม่
- ระบุเส้นทางสำรองที่ปลอดภัยกว่าอย่างชัดเจน
- ไม่ระบุว่าเส้นทางสำรองปลอดภัยกว่าอย่างชัดเจนเมื่อ coverage เป็น `partial`,
  `missing`, `stale`, `unavailable` หรือไม่ทราบ freshness
- ไม่อ้างว่ามีเส้นทางปลอดภัยเมื่อ route context ไม่พร้อมใช้งาน
- ยังไม่คาดการณ์ `safer_later` จนกว่าทีมจะกำหนด contract ของช่วงเวลาภัยให้ชัดเจน

### 4. Contracts และ service facade

- เพิ่ม input models สำหรับ detailed context ของ Module 05
- รองรับ summary context ชั่วคราวที่ Module 03 ใช้กับ mock tools
- เพิ่ม strict output models ให้ตรงกับ draft `RiskResult`, `KnowledgeResult`
  และ `RouteResult` ของ Module 03
- เพิ่ม async service facade เพื่อเตรียมเชื่อม adapter หรือ HTTP API ในขั้นต่อไป
- ไม่ import Module 03 หรือ Module 05 ใน runtime ของ Module 06

## โครงสร้างไฟล์ที่เพิ่ม

```text
06_risk_knowledge_services/
├── IMPLEMENTATION_SUMMARY.md
├── README.md
├── pyproject.toml
├── .gitignore
├── risk_knowledge/
│   ├── __init__.py
│   ├── evidence.py
│   ├── knowledge.py
│   ├── models.py
│   ├── risk.py
│   ├── routing.py
│   └── service.py
└── tests/
    ├── __init__.py
    └── test_services.py
```

## การทดสอบ

ชุดทดสอบครอบคลุม:

- official closure ต้องทำให้ความเสี่ยงเป็น `HIGH`
- fallback เมื่อ integrated context ใช้งานไม่ได้
- การปฏิเสธ feature schema ที่ไม่รองรับ
- การกรองเอกสารหมดอายุและเอกสารที่ยังไม่อนุมัติ
- การไม่สร้างคำแนะนำเมื่อไม่มี active alert
- การปิดเส้นทางหลักและเลือกเส้นทางสำรองที่ปลอดภัยกว่า
- การไม่อ้างว่ามีเส้นทางปลอดภัยเมื่อข้อมูลเส้นทางหาย
- async service facade
- การตรวจ output ของ Module 06 กับ draft schema จริงของ Module 03
- summary context ที่ไม่มี detailed evidence ต้องไม่ถูกประเมินเป็นความเสี่ยงต่ำ
- weather aliases และ quality flags ตาม contract ล่าสุดของ Module 05
- partial route coverage ต้องไม่ถูกประกาศว่าปลอดภัยกว่าอย่างชัดเจน
- transport ของ TomTom และ disaster ของ GDACS ที่ Module 05 จับคู่กับเส้นทางแล้ว
  ต้องถูกประเมิน ขณะที่ `unmatched_evidence` ต้องไม่ถูกนำมาคิดความเสี่ยง

ผลการทดสอบล่าสุด: **ผ่าน 16 จาก 16 tests**

รันการทดสอบจากโฟลเดอร์ Module 06 ด้วยคำสั่ง:

```powershell
python -m unittest discover -s tests -v
```

## Git history

### Feature commit

```text
3c80727 feat(06): add risk knowledge service foundation
```

เพิ่ม provisional contracts, risk baseline, disaster knowledge retrieval,
route analysis, service facade, documentation และ contract-focused tests

### Merge commit เข้า develop

```text
02dd718 merge(06): integrate risk and knowledge services
```

งานถูก merge และ push เข้า `develop` แล้วโดยไม่มี conflict และ diff ของงานมีเฉพาะ
ไฟล์ภายใน `06_risk_knowledge_services`

## งานที่ยังรอข้อตกลงจากทีม

- กำหนด `IntegratedTravelContext` ฉบับสุดท้ายร่วมกับ Module 05
- ตกลงผู้รับผิดชอบ candidate route geometry และ per-segment ETA
- กำหนด semantics ของ polygon (time interval ของ disaster/transport รองรับแล้ว)
- ตกลงความหมายของ confidence ระหว่าง Modules 02, 03, 06 และ 07
- อนุมัติ risk thresholds และชุดเอกสารภัยพิบัติที่จะใช้จริง
- ตกลงพื้นที่ให้บริการและผู้ดูแล emergency contacts
- เพิ่ม calibrated ML model, multilingual embeddings, vector database, monitoring
  และ HTTP adapter หลังจาก cross-module contracts ถูกยืนยันแล้ว
