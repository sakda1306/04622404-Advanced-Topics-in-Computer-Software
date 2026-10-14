import assert from "node:assert/strict";

const base = process.env.WEB_URL ?? "http://localhost:3000";
const outage = process.argv.includes("--outage");
let checks = 0;
function passed(name) {
  checks++;
  console.log("PASS " + name);
}
function client() {
  let cookie = "";
  return async (path, { method = "GET", data, status = 200 } = {}) => {
    const response = await fetch(base + path, {
      method,
      headers: {
        ...(cookie ? { Cookie: cookie } : {}),
        ...(data !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: data === undefined ? undefined : JSON.stringify(data),
      signal: AbortSignal.timeout(65000),
    });
    const setCookie = response.headers.get("set-cookie");
    if (setCookie) cookie = setCookie.split(";")[0];
    const text = await response.text();
    assert.equal(response.status, status, path + ": " + text.slice(0, 300));
    let result;
    try {
      result = JSON.parse(text);
    } catch {
      result = text;
    }
    return { result, response, setCookie };
  };
}
const guest = client();
if (outage) {
  const { result, response } = await guest("/api/chat", {
    method: "POST",
    data: { message: "test", session_id: null },
    status: 502,
  });
  assert.match(
    response.headers.get("content-type"),
    /application\/problem\+json/,
  );
  for (const key of [
    "type",
    "title",
    "status",
    "code",
    "detail",
    "service",
    "request_id",
  ])
    assert.ok(result[key], key);
  assert.equal(result.request_id, response.headers.get("x-request-id"));
  assert.equal(result.service, "web");
  passed("API stopped: proxy emits complete correlated 502 Problem JSON");
} else {
  assert.equal((await guest("/health")).result.status, "ok");
  passed("Docker web health");
  for (const path of [
    "/login",
    "/",
    "/football/standings",
    "/football/fixtures",
    "/football/reports",
    "/football/simulation",
    "/admin",
    "/admin/pipeline",
    "/admin/feedback",
    "/admin/logs",
    "/admin/reports",
    "/admin/audit",
  ]) {
    const { result } = await guest(path);
    assert.match(result, /<html/);
  }
  passed("All 12 page routes served");
  for (const pet of [
    "arsenal",
    "chelsea",
    "liverpool",
    "manchester-city",
    "manchester-united",
  ]) {
    const response = await fetch(base + "/mascots/" + pet + ".webp");
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type"), /image\/webp/);
    assert.ok((await response.arrayBuffer()).byteLength > 100000);
  }
  passed("All five mascot assets served from production image");
  const unauth = await guest("/api/auth/me", { status: 401 });
  assert.match(
    unauth.response.headers.get("content-type"),
    /application\/problem\+json/,
  );
  passed("Unauthenticated request rejected");
  const a = client(),
    b = client(),
    admin = client();
  const login = await a("/api/auth/login", {
    method: "POST",
    data: {
      username: "demo1",
      password: process.env.SEED_DEMO_PASSWORD ?? "demo1234",
    },
  });
  assert.match(login.setCookie, /HttpOnly/i);
  assert.equal(login.result.user.username, "demo1");
  passed("Login cookie passes through web proxy");
  await a("/api/me/preferences", {
    method: "PATCH",
    data: { favorite_team_id: 57 },
  });
  assert.equal((await a("/api/auth/me")).result.user.favorite_team_id, 57);
  passed("Favorite team persisted");
  const { result: answer } = await a("/api/chat", {
    method: "POST",
    data: { session_id: null, message: "อาร์เซนอลแข่งนัดล่าสุดเป็นอย่างไร" },
  });
  assert.ok(answer.answer);
  assert.ok(answer.session_id);
  assert.ok(answer.message_id);
  assert.ok(answer.request_id);
  assert.ok(answer.route);
  passed("Chat request through real API and router stub");
  assert.ok(
    (await a("/api/sessions")).result.sessions.some(
      (session) => session.session_id === answer.session_id,
    ),
  );
  let history;
  for (let attempt = 0; attempt < 10; attempt++) {
    history = (await a("/api/history/" + answer.session_id)).result;
    if (history.messages.length >= 2) break;
    await new Promise((done) => setTimeout(done, 150));
  }
  assert.ok(
    history.messages.some(
      (message) => message.message_id === answer.message_id,
    ),
  );
  passed("Persisted sessions and history");
  let feedback = await fetch(base + "/api/feedback", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: login.setCookie.split(";")[0],
    },
    body: JSON.stringify({
      message_id: answer.message_id,
      rating: -1,
      comment: "Web integration smoke",
    }),
  });
  if (feedback.status === 409)
    feedback = await fetch(base + "/api/feedback", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: login.setCookie.split(";")[0],
      },
      body: JSON.stringify({
        message_id: answer.message_id,
        rating: -1,
        comment: "Web integration smoke",
      }),
    });
  assert.equal(feedback.status, 200);
  passed("Feedback saved");
  const continued = await a("/api/chat", {
    method: "POST",
    data: { session_id: answer.session_id, message: "แล้วตารางคะแนนล่ะ" },
  });
  assert.equal(continued.result.session_id, answer.session_id);
  passed("Follow-up uses same session");
  await a("/api/chat", { method: "POST", data: { message: " " }, status: 422 });
  passed("Blank message validation");
  await a("/api/admin/stats", { status: 403 });
  passed("Normal user forbidden from admin API");
  await a("/api/auth/logout", { method: "POST" });
  await a("/api/auth/me", { status: 401 });
  await b("/api/auth/login", {
    method: "POST",
    data: {
      username: "demo2",
      password: process.env.SEED_DEMO_PASSWORD ?? "demo1234",
    },
  });
  await b("/api/history/" + answer.session_id, { status: 404 });
  assert.ok(
    !(await b("/api/sessions")).result.sessions.some(
      (session) => session.session_id === answer.session_id,
    ),
  );
  passed("Logout and cross-account history isolation");
  const tables = (await b("/api/football/standings")).result;
  assert.ok(Array.isArray(tables.rows));
  const fixtures = (await b("/api/football/fixtures")).result;
  assert.ok(fixtures.matches.length);
  assert.ok(
    (await b("/api/football/matches/" + fixtures.matches[0].match_id)).result
      .home,
  );
  passed("Standings, fixtures and match detail");
  await admin("/api/auth/login", {
    method: "POST",
    data: {
      username: "admin",
      password: process.env.SEED_ADMIN_PASSWORD ?? "admin1234",
    },
  });
  assert.ok((await admin("/api/admin/stats")).result.total_messages >= 2);
  passed("Admin statistics from PostgreSQL");
  await admin("/api/admin/pipeline");
  const job = (
    await admin("/api/admin/pipeline/ingest", {
      method: "POST",
      data: { scope: "fixtures" },
      status: 202,
    })
  ).result;
  assert.equal(
    (await admin("/api/admin/jobs/" + job.job_id)).result.status,
    "done",
  );
  passed("Pipeline submission returns 202 and job completes");
  const generated = (
    await admin("/api/admin/reports/generate", {
      method: "POST",
      data: { season: "2026", matchweek: 5 },
      status: 202,
    })
  ).result;
  assert.ok(generated.job_id);
  passed("Weekly report generation job");
  const reports = (await admin("/api/admin/reports?season=2026")).result.items;
  assert.ok(reports.length);
  let report = reports[0];
  const reportPath =
    "/api/admin/reports/" + report.season + "/" + report.matchweek;
  if (report.status === "published")
    await admin(reportPath + "/unpublish", { method: "POST" });
  await admin(reportPath, {
    method: "PATCH",
    data: { title: report.title, markdown: report.markdown },
  });
  await admin(reportPath + "/publish", { method: "POST" });
  assert.equal(
    (
      await b(
        "/api/football/reports/weekly?season=" +
          report.season +
          "&matchweek=" +
          report.matchweek,
      )
    ).result.status,
    "published",
  );
  await admin(reportPath + "/unpublish", { method: "POST" });
  await b(
    "/api/football/reports/weekly?season=" +
      report.season +
      "&matchweek=" +
      report.matchweek,
    { status: 404 },
  );
  passed("Report edit, publish, public read, unpublish");
  assert.ok(
    (await admin("/api/admin/feedback?rating=-1")).result.items.some(
      (item) => item.message_id === answer.message_id,
    ),
  );
  assert.ok(
    (await admin("/api/admin/messages/" + answer.message_id)).result.answer,
  );
  assert.ok((await admin("/api/admin/logs")).result.items.length);
  assert.ok((await admin("/api/admin/audit")).result.items.length);
  passed("Admin feedback, answer detail, logs and audit");
  const users = (await admin("/api/admin/users?q=demo3")).result.items;
  assert.ok(users.length);
  const third = users[0];
  try {
    assert.equal(
      (
        await admin("/api/admin/users/" + third.id, {
          method: "PATCH",
          data: { disabled: true },
        })
      ).result.disabled,
      true,
    );
  } finally {
    await admin("/api/admin/users/" + third.id, {
      method: "PATCH",
      data: { disabled: false },
    });
  }
  const myself = (await admin("/api/auth/me")).result.user;
  await admin("/api/admin/users/" + myself.id, {
    method: "PATCH",
    data: { role: "user" },
    status: 409,
  });
  passed("User management and self-protection");
  assert.ok((await admin("/api/admin/kb/stats")).result.documents >= 0);
  assert.ok(
    (
      await admin("/api/admin/kb/reindex", {
        method: "POST",
        data: {},
        status: 202,
      })
    ).result.job_id,
  );
  assert.equal(
    (
      await admin("/api/admin/kb/documents/web-smoke-nonexistent", {
        method: "DELETE",
      })
    ).result.deleted,
    false,
  );
  passed("Knowledge Base stats, queued rebuild and single-document deletion");
  const error = await b("/api/chat", {
    method: "POST",
    data: { message: "__error__", session_id: null },
    status: 502,
  });
  assert.ok(error.result.request_id);
  passed("Router failure is 502 with request ID");
  console.log("Waiting for intentional router timeout (~45s)…");
  const timeout = await b("/api/chat", {
    method: "POST",
    data: { message: "__slow__", session_id: null },
    status: 504,
  });
  assert.equal(timeout.result.code, "ROUTER_TIMEOUT");
  passed("Router timeout is 504");
}
console.log(
  "All " +
    checks +
    " integration checks passed. Backend is real; AI and football data use team 02 stubs.",
);
