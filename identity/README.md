# Identity (Keycloak) — ใช้ร่วมกันทั้งทีม

Keycloak ตัวเดียวที่ทุกโมดูลเชื่อถือ ออก JWT ให้ผู้ใช้และ admin ตาม contract ของ
`02_api_backend` (`docs/02_api_spec.md` D-01, `docs/04_project_structure.md` D-101)

> **สำหรับ dev เท่านั้น** — ใช้ H2 ในเครื่อง, HTTP และรหัสผ่านตัวอย่าง ดูหัวข้อ "ก่อนขึ้น production"

## เปิดใช้งาน

```bash
# ที่ root ของ repo
docker compose up -d keycloak
```

- Admin console: http://localhost:8180/admin (ค่าเริ่มต้น `admin` / `admin-dev-change-me`)
- Issuer: `http://localhost:8180/realms/travel-safety`
- Discovery: `http://localhost:8180/realms/travel-safety/.well-known/openid-configuration`

ค่าเริ่มต้นทั้งหมดเปลี่ยนได้ใน `.env` ที่ root (ดู `.env.example` หัวข้อ Keycloak)

## Realm `travel-safety`

ทุก access token มี `iss`, `aud=travel-safety-api`, `sub` และ `scope` (คั่นด้วยเว้นวรรค)
ตามที่ backend ตรวจ, อายุ 15 นาที (P-10)

| Client | ใช้ทำอะไร | Flow | Scope ที่ได้ |
|---|---|---|---|
| `web-app` | 01 Web App — login ผ่าน browser | Authorization code + PKCE (S256), public client ไม่มี secret, redirect `http://localhost:3000/*` | `travel:read` `travel:write` `profile:read` `profile:write` |
| `dev-cli` | **dev เท่านั้น** — ขอ token ด้วย curl/test โดยไม่ต้องเปิด browser | Password grant | เหมือน `web-app` |
| `ops-admin` | งาน admin และ safety review | Client credentials (secret) | `admin:read` `admin:write` `safety:review` |

Scope ของ admin อยู่แค่ใน `ops-admin` — ผู้ใช้ที่ login ผ่าน `web-app`/`dev-cli` ขอ
`admin:*` เองไม่ได้ (Keycloak ตอบ `invalid_scope`)

ผู้ใช้ทดสอบ: `dev-user` / `dev-password-change-me`

## ขอ token

```bash
# ผู้ใช้ทั่วไป
curl -s -X POST http://localhost:8180/realms/travel-safety/protocol/openid-connect/token \
  -d grant_type=password -d client_id=dev-cli \
  -d username=dev-user -d password=dev-password-change-me

# admin
curl -s -X POST http://localhost:8180/realms/travel-safety/protocol/openid-connect/token \
  -d grant_type=client_credentials -d client_id=ops-admin \
  -d client_secret=ops-admin-dev-secret-change-me
```

## โมดูลไหนต้องต่อกับ Keycloak

| โมดูล | ต้องทำอะไร |
|---|---|
| 01 Web App | ใช้ client `web-app` (OIDC library ที่รองรับ PKCE) แล้วส่ง `Authorization: Bearer <access_token>` ไปที่ 02 |
| 02 API Backend | `docker compose -f docker-compose.yml -f docker-compose.keycloak.yml up -d` (ดู README ของ 02) |
| 08 | ต้องต่อด้วย**เฉพาะถ้า**ทีมตัดสินว่า 01 เรียก API ของ 08 ตรง (คำถามที่ยังเปิดอยู่ในทะเบียนสัญญา) |
| 03–07 | ไม่ต้อง — เป็น service ภายในที่ไม่มีผู้ใช้เรียกตรง |

### Container ของโมดูลอื่นเข้าถึง Keycloak ยังไง

`iss` ใน token เป็น `localhost:8180` เสมอ (ตั้ง `KC_HOSTNAME` ตายตัว) แต่ `localhost`
ใน container คือตัว container เอง ดังนั้นฝั่งที่ตรวจ token ใน Docker ให้:

- ตั้ง issuer ที่ต้องตรวจเป็น `http://localhost:8180/realms/travel-safety` (ตรงกับ `iss`)
- ดึงกุญแจจาก `http://host.docker.internal:8180/realms/travel-safety/protocol/openid-connect/certs`
- ใส่ `extra_hosts: ["host.docker.internal:host-gateway"]` ให้ใช้ได้บน Linux ด้วย

## แก้ realm

Keycloak import realm แค่ตอนที่ realm ยังไม่มี (`IGNORE_EXISTING`) ถ้าแก้
`keycloak/realm-travel-safety.json` ต้องล้าง volume ก่อน:

```bash
docker compose down -v && docker compose up -d keycloak
```

ถ้าแก้ผ่าน admin console แล้วอยากเก็บไว้ ให้ export กลับมาเป็นไฟล์นี้ แล้วแทนค่า secret/password
ด้วย `${KC_OPS_ADMIN_SECRET}` / `${KC_DEV_USER_PASSWORD}` เหมือนเดิม — ห้าม commit ค่าจริง

## ก่อนขึ้น production

- ใช้ Postgres แทน H2 และรันด้วย `start` (ไม่ใช่ `start-dev`) หลัง HTTPS
- ลบ client `dev-cli` และผู้ใช้ `dev-user`
- เปลี่ยน admin จาก client secret ร่วมเป็น login รายคน และให้ได้ scope admin ตาม role เท่านั้น
- ตั้ง redirect URI และ web origin ของ `web-app` เป็นโดเมนจริง
