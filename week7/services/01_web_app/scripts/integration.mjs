import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const routes = ["football_rag", "general_ai", "local_ai", "clarify", "decline"];

export function validateCases(cases) {
  assert.ok(
    Array.isArray(cases) && cases.length >= 2,
    "Provide at least two verified cases",
  );
  for (const item of cases) {
    assert.ok(
      typeof item.name === "string" && item.name.trim(),
      "Case name required",
    );
    assert.ok(
      typeof item.message === "string" &&
        item.message.trim() &&
        item.message.length <= 2000,
      "Valid message required",
    );
    assert.ok(routes.includes(item.expectedRoute), "Expected route required");
    assert.ok(
      Array.isArray(item.expectedDocIds),
      "Expected document IDs required (empty for no sources)",
    );
    assert.ok(
      item.expectedDocIds.every((id) => typeof id === "string" && id.trim()),
      "Invalid document ID",
    );
    assert.ok(
      Array.isArray(item.expectedAnswerIncludes) &&
        item.expectedAnswerIncludes.length > 0 &&
        item.expectedAnswerIncludes.every(
          (part) => typeof part === "string" && part.trim(),
        ),
      "Verified answer fragments required",
    );
    if (item.expectedDataAsOf !== undefined && item.expectedDataAsOf !== null)
      assert.ok(
        Number.isFinite(Date.parse(item.expectedDataAsOf)),
        "Invalid expected data_as_of",
      );
    if (item.expectedFallback !== undefined)
      assert.ok(
        item.expectedFallback === null ||
          typeof item.expectedFallback === "string",
        "Invalid expected fallback",
      );
  }
  assert.ok(
    cases.some(
      (item) =>
        item.expectedRoute === "football_rag" && item.expectedDocIds.length,
    ),
    "Include a grounded answer case",
  );
  assert.ok(
    cases.some((item) => !item.expectedDocIds.length),
    "Include a clarification or no-data case",
  );
  return cases;
}

export function verifyAnswer(answer, item) {
  assert.ok(
    answer && typeof answer.answer === "string" && answer.answer.trim(),
    "Missing answer",
  );
  for (const key of ["session_id", "message_id", "request_id"])
    assert.ok(typeof answer[key] === "string" && answer[key], `Missing ${key}`);
  assert.equal(answer.route, item.expectedRoute, "Unexpected route");
  assert.ok(Array.isArray(answer.sources), "Missing sources");
  assert.deepEqual(
    [...new Set(answer.sources.map((source) => source.doc_id))].sort(),
    [...new Set(item.expectedDocIds)].sort(),
    "Sources do not match the verified dataset",
  );
  const refs = new Set();
  for (const source of answer.sources) {
    assert.ok(
      Number.isInteger(source.ref) && source.ref > 0 && !refs.has(source.ref),
      "Invalid or duplicate source ref",
    );
    refs.add(source.ref);
    assert.ok(source.title?.trim(), "Missing source title");
    assert.ok(
      answer.answer.includes(`[${source.ref}]`),
      "Source is not cited in the answer",
    );
    if (source.fetched_at != null)
      assert.ok(
        Number.isFinite(Date.parse(source.fetched_at)),
        "Invalid source timestamp",
      );
  }
  for (const match of answer.answer.matchAll(/\[(\d+)\]/g))
    assert.ok(refs.has(Number(match[1])), "Citation has no matching source");
  for (const part of item.expectedAnswerIncludes)
    assert.ok(
      answer.answer.includes(part),
      "Answer does not match the verified facts",
    );
  assert.ok(Object.hasOwn(answer, "data_as_of"), "Missing data_as_of field");
  if (answer.data_as_of !== null)
    assert.ok(
      Number.isFinite(Date.parse(answer.data_as_of)),
      "Invalid data_as_of",
    );
  if (Object.hasOwn(item, "expectedDataAsOf"))
    assert.equal(
      answer.data_as_of,
      item.expectedDataAsOf,
      "Unexpected data_as_of",
    );
  if (Object.hasOwn(item, "expectedFallback"))
    assert.equal(
      answer.trace?.fallback ?? null,
      item.expectedFallback,
      "Unexpected fallback",
    );
}

export async function runIntegration({
  base,
  accounts,
  cases,
  fetcher = fetch,
  log = console.log,
}) {
  validateCases(cases);
  const url = new URL(base);
  assert.ok(
    ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash &&
      url.pathname === "/",
    "WEB_URL must be an HTTP(S) origin without credentials",
  );
  assert.equal(accounts.length, 2, "Two test accounts required");
  assert.ok(
    accounts.every((account) => account.username?.trim() && account.password),
    "Test account credentials required",
  );
  assert.notEqual(
    accounts[0].username,
    accounts[1].username,
    "Use two distinct accounts",
  );
  let checks = 0;
  const pass = (name) => {
    checks++;
    log(`PASS ${name}`);
  };
  const client = () => {
    let cookie = "";
    return async (path, { method = "GET", data, status = 200 } = {}) => {
      const response = await fetcher(new URL(path, url), {
        method,
        headers: {
          ...(cookie ? { Cookie: cookie } : {}),
          ...(data === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: data === undefined ? undefined : JSON.stringify(data),
        signal: AbortSignal.timeout(65000),
      });
      const setCookie = response.headers.get("set-cookie");
      if (setCookie) cookie = setCookie.split(";")[0];
      // Never print response bodies: they can contain account or conversation data.
      assert.equal(
        response.status,
        status,
        `${method} ${path}: unexpected HTTP status`,
      );
      const result = await response.json();
      return { result, response };
    };
  };
  const a = client(),
    b = client();
  const active = [];
  let failure;
  try {
    assert.equal((await a("/health")).result.status, "ok");
    await a("/api/auth/me", { status: 401 });
    pass("Health and guest access");
    for (const [index, call] of [a, b].entries()) {
      const { result, response } = await call("/api/auth/login", {
        method: "POST",
        data: accounts[index],
      });
      active.push(call);
      assert.equal(result.user.username, accounts[index].username);
      assert.equal(result.user.role, "user", "Use ordinary test users");
      assert.match(response.headers.get("set-cookie") ?? "", /HttpOnly/i);
    }
    pass("Two independent authenticated accounts");
    for (const item of cases) {
      const { result: answer, response } = await a("/api/chat", {
        method: "POST",
        data: { session_id: null, message: item.message },
      });
      verifyAnswer(answer, item);
      assert.equal(
        response.headers.get("x-request-id"),
        answer.request_id,
        "Request ID mismatch",
      );
      let history;
      for (let attempt = 0; attempt < 20; attempt++) {
        history = (await a(`/api/history/${answer.session_id}`)).result;
        if (
          history.messages?.some(
            (message) => message.message_id === answer.message_id,
          )
        )
          break;
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      const saved = history.messages.find(
        (message) => message.message_id === answer.message_id,
      );
      assert.ok(saved, "Answer did not persist within 5 seconds");
      assert.equal(saved.content, answer.answer);
      assert.deepEqual(saved.sources, answer.sources);
      assert.equal(saved.route, answer.route);
      const sessions = (await a("/api/sessions")).result.sessions;
      assert.ok(
        sessions.some((session) => session.session_id === answer.session_id),
      );
      await b(`/api/history/${answer.session_id}`, { status: 404 });
      assert.ok(
        !(await b("/api/sessions")).result.sessions.some(
          (session) => session.session_id === answer.session_id,
        ),
      );
      await a("/api/feedback", {
        method: "POST",
        data: {
          message_id: answer.message_id,
          rating: 1,
          comment: "Web integration verification",
        },
      });
      const rated = (
        await a(`/api/history/${answer.session_id}`)
      ).result.messages.find(
        (message) => message.message_id === answer.message_id,
      );
      assert.equal(rated.rating, 1);
      pass(`${item.name}: answer, citations, history, isolation and feedback`);
    }
    await a("/api/admin/stats", { status: 403 });
    const standings = (await a("/api/football/standings")).result;
    const fixtures = (await a("/api/football/fixtures")).result;
    assert.ok(
      Array.isArray(standings.rows) && standings.rows.length,
      "Seed standings before running integration",
    );
    assert.ok(
      Array.isArray(fixtures.matches) && fixtures.matches.length,
      "Seed fixtures before running integration",
    );
    const fixture = fixtures.matches[0];
    const detail = (
      await a(`/api/football/matches/${encodeURIComponent(fixture.match_id)}`)
    ).result;
    assert.equal(detail.match_id, fixture.match_id);
    assert.equal(detail.home.team_id, fixture.home.team_id);
    assert.equal(detail.away.team_id, fixture.away.team_id);
    pass("Football data and admin access restrictions");
  } catch (error) {
    failure = error;
  } finally {
    for (const call of active) {
      try {
        await call("/api/auth/logout", { method: "POST" });
        await call("/api/auth/me", { status: 401 });
      } catch (error) {
        failure ??= error;
      }
    }
  }
  if (failure) throw failure;
  pass("Logout clears both sessions");
  log(
    `${checks} HTTP integration checks passed. Verify service versions and browser rendering separately.`,
  );
  return checks;
}

async function main() {
  assert.ok(
    process.env.INTEGRATION_CASES,
    "Set INTEGRATION_CASES to a JSON file with facts verified against the test database",
  );
  const cases = JSON.parse(
    await readFile(process.env.INTEGRATION_CASES, "utf8"),
  );
  await runIntegration({
    base: process.env.WEB_URL ?? "http://localhost:3000",
    accounts: [
      {
        username: process.env.INTEGRATION_USER_A,
        password: process.env.INTEGRATION_PASSWORD_A,
      },
      {
        username: process.env.INTEGRATION_USER_B,
        password: process.env.INTEGRATION_PASSWORD_B,
      },
    ],
    cases,
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
