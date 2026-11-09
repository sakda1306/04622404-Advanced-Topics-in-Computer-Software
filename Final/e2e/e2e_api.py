"""End-to-end API test through the web proxy (http://localhost:3000/api).

Runs test groups A-F (README.md) against the running docker stack and prints
PASS / FAIL per check. Test accounts are deleted at the end. Every run is also
written to e2e/runs/<timestamp>_<commit>.log so runs can be compared later.
"""
import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("E2E_BASE", "http://localhost:3000/api")
STAMP = time.strftime("%H%M%S")
USER_EMAIL = f"e2e-{STAMP}@example.com"
ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "e2e-admin@example.com")  # must be in ADMIN_EMAILS
PASSWORD = "e2e-Passw0rd-" + STAMP

results = []
notes = []


def _git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


class _Tee:
    """Print to the terminal and to the run log at the same time."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for st in self.streams:
            st.write(data)

    def flush(self):
        for st in self.streams:
            st.flush()


RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
os.makedirs(RUNS_DIR, exist_ok=True)
_started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
_commit = _git("rev-parse", "--short", "HEAD")
_log = open(os.path.join(RUNS_DIR, f"{time.strftime('%Y-%m-%d_%H%M%S')}_{_commit}.log"), "w", encoding="utf-8")
sys.stdout = _Tee(sys.__stdout__, _log)
print(f"run started: {_started}")
print(f"branch: {_git('rev-parse', '--abbrev-ref', 'HEAD')}  commit: {_commit}  uncommitted files: {len(_git('status', '--porcelain').splitlines())}")
print(f"base: {BASE}  admin: {ADMIN_EMAIL}\n")


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  -- {detail}" if detail and not ok else ""), flush=True)
    return ok


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method, path, body=None, raw=None, ctype=None, timeout=180):
        headers = {}
        data = None
        if raw is not None:
            data, headers["Content-Type"] = raw, ctype
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
        t = time.time()
        try:
            res = self.opener.open(req, timeout=timeout)
            status, hdrs, text = res.status, res.headers, res.read().decode()
        except urllib.error.HTTPError as e:
            status, hdrs, text = e.code, e.headers, e.read().decode()
        try:
            js = json.loads(text) if text else None
        except ValueError:
            js = None
        return status, js, hdrs, round(time.time() - t, 1)

    def upload(self, filename, content, ctype):
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        return self.call("POST", "/cv", raw=body, ctype=f"multipart/form-data; boundary={boundary}")


def pdf(lines):
    """Minimal one-page PDF with a real text layer (Helvetica)."""
    ops = ["BT /F1 11 Tf 50 800 Td 14 TL"]
    for line in lines:
        esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"({esc}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


CV_LINES = [
    "Somchai Testuser",
    "Email: candidate@example.com",
    "",
    "Skills",
    "Python, SQL, JavaScript, React, Docker, Git, Linux, REST API",
    "",
    "Experience",
    "Backend Developer Intern - Example Co., Ltd.",
    "Jun 2024 - Dec 2024",
    "Built REST APIs with Python and FastAPI, wrote SQL queries on PostgreSQL.",
    "",
    "Education",
    "Bachelor of Engineering, Computer Engineering",
    "Rajamangala University of Technology Thanyaburi, 2021 - 2025",
]


def quota_headers_ok(hdrs):
    return hdrs.get("x-quota-requests-remaining") is not None


def main():
    # ---------------- A. Health and auth ----------------
    anon = Client()
    s, js, _, _ = anon.call("GET", "/health")
    check("A1 health ok", s == 200 and js and js.get("status") == "ok", f"{s} {js}")

    u = Client()
    reg = {"email": USER_EMAIL, "password": PASSWORD, "display_name": "ทดสอบ E2E", "consent": True}
    s, js, _, _ = u.call("POST", "/auth/register", reg)
    check("A2 register 200 + user", s == 200 and js and js["user"]["email"] == USER_EMAIL, f"{s} {js}")
    s, js, _, _ = anon.call("POST", "/auth/register", reg)
    check("A2 duplicate email -> 409 EMAIL_TAKEN", s == 409 and js and js.get("code") == "EMAIL_TAKEN", f"{s} {js}")
    s, js, _, _ = anon.call("POST", "/auth/register", {**reg, "email": f"short-{STAMP}@example.com", "password": "short"})
    check("A2 short password -> 422", s == 422 and js and js.get("code") == "VALIDATION_ERROR", f"{s} {js}")
    s, js, _, _ = anon.call("POST", "/auth/register", {**reg, "email": f"noconsent-{STAMP}@example.com", "consent": False})
    check("A2 consent false -> 422", s == 422, f"{s} {js}")
    check("A2 error has Thai message_th", bool(js and js.get("message_th")), f"{js}")

    s, js, _, _ = anon.call("POST", "/auth/login", {"email": USER_EMAIL, "password": "wrong-password"})
    check("A3 wrong password -> 401 INVALID_CREDENTIALS", s == 401 and js.get("code") == "INVALID_CREDENTIALS", f"{s} {js}")
    rl_email = f"ratelimit-{STAMP}@example.com"
    codes = [anon.call("POST", "/auth/login", {"email": rl_email, "password": "x" * 8})[0] for _ in range(6)]
    check("A3 6th failed login in a minute -> 429", codes[-1] == 429, f"codes {codes}")
    login = Client()
    s, js, _, _ = login.call("POST", "/auth/login", {"email": USER_EMAIL, "password": PASSWORD})
    check("A3 login 200", s == 200 and js["user"]["email"] == USER_EMAIL, f"{s} {js}")

    s, js, _, _ = anon.call("GET", "/auth/me")
    check("A4 me without cookie -> 401 UNAUTHENTICATED", s == 401 and js.get("code") == "UNAUTHENTICATED", f"{s} {js}")
    s, js, hdrs, _ = u.call("GET", "/auth/me")
    check("A4 me with cookie -> 200, is_admin false", s == 200 and js["user"]["is_admin"] is False, f"{s} {js}")
    check("F16 X-Quota-* headers on authenticated response", quota_headers_ok(hdrs), dict(hdrs))

    # ---------------- B. CV ----------------
    s, js, _, _ = u.upload("notes.txt", b"just text, not a pdf", "text/plain")
    check("B5 non-PDF -> 415 CV_INVALID_TYPE", s == 415 and js.get("code") == "CV_INVALID_TYPE", f"{s} {js}")
    big = pdf(CV_LINES)[:-6] + b" " * (5 * 1024 * 1024 + 10) + b"%%EOF\n"
    s, js, _, _ = u.upload("big.pdf", big, "application/pdf")
    check("B5 >5 MB -> 413 CV_TOO_LARGE", s == 413 and js and js.get("code") == "CV_TOO_LARGE", f"{s} {js}")
    s, js, _, _ = u.upload("scan.pdf", pdf([]), "application/pdf")
    check("B5 PDF with no text -> 422 CV_UNREADABLE", s == 422 and js.get("code") == "CV_UNREADABLE", f"{s} {js}")
    s, js, _, t = u.upload("cv.pdf", pdf(CV_LINES), "application/pdf")
    ok = check("B5 text PDF -> 200 draft", s == 200 and js["cv"]["status"] == "draft", f"{s} {js}")
    if ok:
        cv = js["cv"]
        notes.append(f"CV parse ({t}s): {len(cv['skills'])} skills {[x['name'] for x in cv['skills']]}, "
                     f"{len(cv['experience'])} experience, {len(cv['education'])} education, warnings {cv['warnings_th']}")
        check("B5 parser found skills", len(cv["skills"]) >= 3, f"{cv['skills']}")
    s, js, _, _ = u.call("GET", "/cv")
    check("B6 GET /cv returns the draft", s == 200 and js["cv"] and js["cv"]["status"] == "draft", f"{s} {js}")
    cv = js["cv"]
    skills = [{**sk, "level": sk.get("level") or 3} for sk in cv["skills"]]
    exp = cv["experience"] or [{"title": "Backend Developer Intern", "company": "Example Co., Ltd.", "start": "2024-06", "end": "2024-12", "months": 6}]
    edu = cv["education"] or [{"school": "RMUTT", "degree": "ปริญญาตรี", "field": "Computer Engineering"}]
    s, js, _, _ = u.call("PUT", "/cv/confirm", {"skills": skills, "education": edu, "experience": exp})
    ok = check("B6 confirm -> 200 confirmed + completeness", s == 200 and js["cv"]["status"] == "confirmed" and "score" in js["completeness"], f"{s} {js}")
    if ok:
        c = js["completeness"]
        notes.append(f"Completeness after CV: {c['score']} can_generate={c['can_generate']} missing_required={c['missing_required']} inputs={c['inputs']}")

    # ---------------- C. Questionnaire ----------------
    s, qn, _, _ = u.call("GET", "/questionnaire")
    att = (qn or {}).get("attribution") or {}
    check("C7 questionnaire sections", s == 200 and len(qn.get("sections", [])) > 0, f"{s}")
    check("C7 attribution Thai text + O*NET sources", "O*NET" in att.get("text_th", "") and len(att.get("sources", [])) >= 1, f"{att}")
    questions = [q for sec in qn["sections"] for q in sec["questions"]]
    types = {}
    for q in questions:
        types[q["type"]] = types.get(q["type"], 0) + 1
    notes.append(f"Questionnaire: {len(qn['sections'])} sections, {len(questions)} questions, types {types}")
    saved_fail = []
    multi_q = None
    for q in questions:
        t = q["type"]
        if t == "single":
            v = q["options"][0]["value"]
        elif t == "multi":
            multi_q = multi_q or q
            v = [o["value"] for o in q["options"][: min(2, q.get("max_choices") or 2)]]
        elif t == "scale":
            v = 4
        elif t == "skill_checklist":
            v = [{"skill_id": o["value"], "level": 3} for o in q["options"][:4]]
        else:
            v = "ตอนทำโปรเจกต์จบ ฉันเป็นคนประสานงานกับอาจารย์และแบ่งงานในทีม"
        s, js, _, _ = u.call("PUT", f"/questionnaire/answers/{q['question_id']}", {"value": v})
        if s != 200 or not js.get("saved"):
            saved_fail.append((q["question_id"], t, s, js))
    check(f"C8 save all {len(questions)} answers (every type)", not saved_fail, f"{saved_fail[:3]}")
    s, js, _, _ = u.call("PUT", "/questionnaire/answers/no-such-question", {"value": "x"})
    check("C8 unknown question -> 404 QUESTION_NOT_FOUND", s == 404 and js.get("code") == "QUESTION_NOT_FOUND", f"{s} {js}")
    if multi_q and multi_q.get("max_choices") and len(multi_q["options"]) > multi_q["max_choices"]:
        v = [o["value"] for o in multi_q["options"][: multi_q["max_choices"] + 1]]
        s, js, _, _ = u.call("PUT", f"/questionnaire/answers/{multi_q['question_id']}", {"value": v})
        check("C8 too many choices -> 422", s == 422, f"{s} {js}")
        # put the valid answer back
        u.call("PUT", f"/questionnaire/answers/{multi_q['question_id']}", {"value": v[:1]})
    s, js, _, _ = u.call("GET", "/questionnaire/answers")
    check("C8 resume: answered == total", s == 200 and js["answered"] == len(questions), f"{s} answered={js and js.get('answered')} total={js and js.get('total')}")

    # ---------------- D. Profile and roles ----------------
    fresh = Client()
    fresh_email = f"e2e-empty-{STAMP}@example.com"
    fresh.call("POST", "/auth/register", {**reg, "email": fresh_email})
    s, js, _, _ = fresh.call("POST", "/profile/generate")
    check("D9 generate with no data -> 409 PROFILE_NOT_READY + details.missing",
          s == 409 and js.get("code") == "PROFILE_NOT_READY" and (js.get("details") or {}).get("missing"), f"{s} {js}")
    s, js, _, _ = fresh.call("GET", "/profile")
    check("D9 GET /profile before generate -> null or 404", (s == 200 and js.get("profile") is None) or (s == 404 and js.get("code") == "PROFILE_NOT_FOUND"), f"{s} {js}")
    fresh.call("DELETE", "/me", {"confirm": "DELETE"})

    s, comp, _, _ = u.call("GET", "/profile/completeness")
    check("D9 completeness can_generate", s == 200 and comp["can_generate"], f"{s} {comp}")
    notes.append(f"Completeness before generate: {comp.get('score')} slots_filled={[x['slot'] for x in comp.get('slots', []) if x['filled']]}")
    s, js, hdrs, t = u.call("POST", "/profile/generate")
    ok = check("D9 generate -> 200 profile + matches", s == 200 and js.get("profile") and js.get("matches"), f"{s} {js}")
    notes.append(f"Profile generate took {t}s")
    if not ok:
        return
    prof, matches = js["profile"], js["matches"]
    hard = prof["hard_skills"]
    check("D9 every skill has evidence", all(sk["evidence_ids"] and all(e in prof["evidence"] for e in sk["evidence_ids"]) for sk in hard + prof["soft_skills"]),
          "missing evidence")
    check("D9 work-style disclaimer text", prof["work_style"]["disclaimer_th"] == "ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ", prof["work_style"]["disclaimer_th"])
    notes.append(f"Profile: {len(hard)} hard skills, {len(prof['soft_skills'])} soft skills, {len(prof['blind_spots'])} blind spots, "
                 f"experience {prof['experience']['total_months']} months")
    check("D10 matches <= 5, threshold present", len(matches["roles"]) <= 5 and "threshold" in matches, f"{matches}")
    notes.append("Matches: " + ", ".join(f"{m['role_id']} {m['match_pct']}%" for m in matches["roles"])
                 + f" (threshold {matches['threshold']}, below_threshold={matches['below_threshold']})")
    check("D10 match_pct are integers 0-100", all(isinstance(m["match_pct"], int) and 0 <= m["match_pct"] <= 100 for m in matches["roles"]),
          [m["match_pct"] for m in matches["roles"]])
    check("D10 each next step is tied to a gap", all({n["gap_id"] for n in m["next_steps"]} <= {g["gap_id"] for g in m["gaps"]} for m in matches["roles"]), "orphan next step")

    s, js, _, _ = u.call("GET", "/profile")
    check("D10 GET /profile", s == 200 and js["profile"]["profile_version"] == prof["profile_version"], f"{s}")
    s, js, _, _ = u.call("GET", "/roles")
    check("D10 GET /roles -> 26 roles", s == 200 and len(js["roles"]) == 26, f"{s} {len((js or {}).get('roles', []))}")
    s, js, _, _ = u.call("GET", "/roles/matches")
    check("D10 GET /roles/matches", s == 200 and len(js["roles"]) == len(matches["roles"]), f"{s}")
    role_id = matches["roles"][0]["role_id"]
    s, js, _, _ = u.call("GET", f"/roles/{role_id}")
    check("D10 GET /roles/{id} role + match", s == 200 and js["role"]["role_id"] == role_id and js["match"], f"{s}")
    s, js, _, _ = u.call("GET", "/roles/no-such-role")
    check("D10 unknown role -> 404 ROLE_NOT_FOUND", s == 404 and js.get("code") == "ROLE_NOT_FOUND", f"{s} {js}")

    target = hard[0]
    s, js, _, _ = u.call("DELETE", f"/profile/skills/{target['skill_id']}")
    ok = check(f"D11 remove skill {target['skill_id']}", s == 200 and target["skill_id"] not in [x["skill_id"] for x in js["profile"]["hard_skills"]], f"{s} {js}")
    stale_after_remove = ok and any(m["explanations_stale"] for m in js["matches"]["roles"])
    notes.append(f"After remove: stale roles = {[m['role_id'] for m in js['matches']['roles'] if m['explanations_stale']]}" if ok else "")
    s, js, _, _ = u.call("GET", "/profile/removed-skills")
    check("D11 removed list has the skill", s == 200 and target["skill_id"] in [x["skill_id"] for x in js["skills"]], f"{s} {js}")
    s, js, _, _ = u.call("POST", f"/profile/skills/{target['skill_id']}/restore")
    check("D11 restore skill", s == 200 and target["skill_id"] in [x["skill_id"] for x in js["profile"]["hard_skills"]], f"{s} {js}")
    s, js, _, _ = u.call("GET", "/profile/removed-skills")
    check("D11 removed list empty after restore", s == 200 and target["skill_id"] not in [x["skill_id"] for x in js["skills"]], f"{s} {js}")
    s, js, _, _ = u.call("PATCH", "/profile/preferences", {"desired_salary_thb": 30000})
    check("D11 PATCH preferences salary", s == 200 and js["profile"]["preferences"].get("desired_salary_thb") == 30000, f"{s} {js}")

    s, js, _, _ = u.call("GET", "/roles/matches")
    stale = [m["role_id"] for m in js["roles"] if m["explanations_stale"]]
    notes.append(f"Stale before explain: {stale} (stale right after remove: {stale_after_remove})")
    s, js, _, t = u.call("POST", "/roles/matches/explain")
    check("D12 explain -> no stale roles", s == 200 and not any(m["explanations_stale"] for m in js["roles"]), f"{s} {js}")
    notes.append(f"Explain took {t}s")

    s, mk, _, _ = u.call("GET", f"/roles/{role_id}/market?listings=5")
    ok = check("D13 market 200, bangkok, disclaimer", s == 200 and mk["location_scope"] == "bangkok" and mk["disclaimer_th"], f"{s} {mk}")
    if ok:
        notes.append(f"Market {role_id}: available={mk['available']} stale={mk['stale']} refreshing={mk['refreshing']} "
                     f"layers={[k for k, v in mk['salary'].items() if v]} listings={len(mk['listings'])} "
                     f"postings={(mk['demand'] or {}).get('posting_count')}")
        check("D13 listings have no contact fields", all(set(l) <= {"title", "company", "location", "salary_text", "posted_at", "url", "source"} for l in mk["listings"]),
              [sorted(l) for l in mk["listings"][:1]])
        check("D13 listings <= 5", len(mk["listings"]) <= 5, len(mk["listings"]))

    # ---------------- E. Chat and edits ----------------
    chat_cases = [
        ("salary", "เงินเดือนเริ่มต้นของสายงานนี้ในกรุงเทพฯ ประมาณเท่าไร"),
        ("skill", "ทักษะไหนของฉันเด่นที่สุด"),
        ("off-topic", "ช่วยแต่งกลอนเรื่องแมวให้หน่อย"),
    ]
    for label, msg in chat_cases:
        s, js, hdrs, t = u.call("POST", "/chat", {"message": msg})
        ok = check(f"E14 chat {label} -> 200 answer", s == 200 and js.get("answer"), f"{s} {js}")
        if ok:
            check(f"E14 chat {label} quota headers", quota_headers_ok(hdrs), "")
            notes.append(f"Chat {label} ({t}s): route={js['route']} sources={len(js['sources'])} tokens={js['tokens_used']} answer={js['answer'][:120]!r}")
    s, js, _, _ = u.call("POST", "/chat", {"message": "ก" * 1001})
    check("E14 chat > 1000 chars -> 422", s == 422, f"{s} {js}")
    s, js, _, _ = u.call("GET", "/chat/history?limit=50")
    check("E14 chat history has user + assistant messages", s == 200 and len(js["messages"]) >= 6, f"{s} {len((js or {}).get('messages', []))}")

    edit_ids = []
    for msg in [f"เปลี่ยนระดับ {target['name_en']} เป็น 4", "เพิ่มทักษะ Kubernetes ระดับ 1"]:
        s, js, _, t = u.call("POST", "/chat", {"message": msg})
        ep = js.get("edit_proposal") if s == 200 else None
        check(f"E15 chat edit request -> proposal ({msg})", s == 200 and js["route"] == "profile_edit" and ep, f"{s} route={js and js.get('route')} answer={js and js.get('answer', '')[:150]}")
        if ep:
            edit_ids.append(ep["edit_id"])
            notes.append(f"Edit proposal: {ep['summary_th']} changes={ep['changes']}")
    s, js, _, _ = u.call("GET", "/profile/edits/pending")
    check("E15 pending edits listed", s == 200 and {e["edit_id"] for e in js["edits"]} >= set(edit_ids), f"{s} {js}")
    if edit_ids:
        before = u.call("GET", "/profile")[1]["profile"]["profile_version"]
        s, js, _, _ = u.call("POST", f"/profile/edits/{edit_ids[0]}/confirm")
        check("E15 confirm edit -> profile updated", s == 200 and js["profile"]["profile_version"] >= before, f"{s} {js}")
        s, js, _, _ = u.call("POST", f"/profile/edits/{edit_ids[0]}/confirm")
        check("E15 confirm same edit again -> 4xx", 400 <= s < 500, f"{s} {js}")
    if len(edit_ids) > 1:
        s, js, _, _ = u.call("POST", f"/profile/edits/{edit_ids[1]}/reject")
        check("E15 reject edit", s == 200 and js.get("ok"), f"{s} {js}")
    s, js, _, _ = u.call("POST", "/profile/edits/00000000-0000-0000-0000-000000000000/confirm")
    check("E15 unknown edit -> 404 EDIT_NOT_FOUND", s == 404 and js.get("code") == "EDIT_NOT_FOUND", f"{s} {js}")

    # ---------------- F. Quota, admin, cleanup ----------------
    s, q, hdrs, _ = u.call("GET", "/quota")
    ok = check("F16 GET /quota", s == 200 and q["requests_used"] > 0, f"{s} {q}")
    if ok:
        rem = int(hdrs.get("x-quota-requests-remaining"))
        check("F16 header remaining == limit - used", rem == q["requests_limit"] - q["requests_used"], f"header {rem}, body {q}")
        notes.append(f"Quota after test: {q['requests_used']}/{q['requests_limit']} requests, {q['tokens_used']}/{q['tokens_limit']} tokens")

    s, js, _, _ = u.call("GET", "/admin/overview")
    check("F17 admin as normal user -> 403 FORBIDDEN", s == 403 and js.get("code") == "FORBIDDEN", f"{s} {js}")
    adm = Client()
    s, js, _, _ = adm.call("POST", "/auth/register", {**reg, "email": ADMIN_EMAIL})
    if s == 409:
        s, js, _, _ = adm.call("POST", "/auth/login", {"email": ADMIN_EMAIL, "password": PASSWORD})
    check("F17 temp admin is_admin true", s == 200 and js["user"]["is_admin"] is True, f"{s} {js}")
    for w in ["today", "7d", "30d"]:
        s, js, _, t = adm.call("GET", f"/admin/overview?window={w}")
        ok = check(f"F17 admin overview window={w}", s == 200 and js["window"] == w, f"{s} {js}")
        if ok:
            text = json.dumps(js, ensure_ascii=False)
            check(f"F17 overview {w} has no emails", "@" not in text, "found '@' in admin payload")
            if w == "today":
                notes.append(f"Admin today: requests={js['health']['requests']} error_rate={js['health']['error_rate']} "
                             f"db={js['health']['db']} warnings={[x['code'] for x in js['warnings']]} "
                             f"llm={[(m['model'], m['requests_used']) for m in js['llm']['models']]} "
                             f"cache_roles={len(js['cache']['roles'])} router_messages={js['router']['messages']} ({t}s)")
    adm.call("DELETE", "/me", {"confirm": "DELETE"})

    s, js, _, _ = login.call("POST", "/auth/logout")
    check("F18 logout", s == 200 and js.get("ok"), f"{s} {js}")
    s, js, _, _ = login.call("GET", "/auth/me")
    check("F18 me after logout -> 401", s == 401, f"{s}")
    s, js, _, _ = u.call("DELETE", "/me", {"confirm": "delete"})
    check("F18 delete with wrong word -> 422", s == 422, f"{s} {js}")
    s, js, _, _ = u.call("DELETE", "/me", {"confirm": "DELETE"})
    check("F18 delete account", s == 200 and js.get("deleted"), f"{s} {js}")
    s, js, _, _ = anon.call("POST", "/auth/login", {"email": USER_EMAIL, "password": PASSWORD})
    check("F18 login after delete -> 401", s == 401, f"{s} {js}")


try:
    main()
except Exception as e:  # report and keep the summary
    import traceback
    traceback.print_exc()
    check("script finished without exception", False, repr(e))

print("\n--- notes")
for n in notes:
    if n:
        print("*", n)
failed = [r for r in results if not r[1]]
print(f"\n--- {len(results) - len(failed)} passed, {len(failed)} failed  (finished {time.strftime('%Y-%m-%dT%H:%M:%S%z')})")
for name, _, detail in failed:
    print("FAIL", name, "--", str(detail)[:600])
sys.exit(1 if failed else 0)
