import assert from "node:assert/strict";
import { test } from "node:test";
import {
  runIntegration,
  validateCases,
  verifyAnswer,
} from "../scripts/integration.mjs";

// Synthetic responses test the runner itself, not real football or AI quality.
const cases = [
  {
    name: "Grounded",
    message: "known question",
    expectedRoute: "football_rag",
    expectedDocIds: ["fixture-1"],
    expectedAnswerIncludes: ["verified fact"],
    expectedDataAsOf: "2026-09-24T00:00:00Z",
    expectedFallback: null,
  },
  {
    name: "Clarify",
    message: "unclear question",
    expectedRoute: "clarify",
    expectedDocIds: [],
    expectedAnswerIncludes: ["Which team"],
    expectedDataAsOf: null,
  },
];
const grounded = {
  answer: "verified fact [1]",
  session_id: "session-1",
  message_id: "message-1",
  request_id: "request-1",
  route: "football_rag",
  sources: [
    {
      ref: 1,
      doc_id: "fixture-1",
      title: "Verified fact",
      fetched_at: "2026-09-24T00:00:00Z",
    },
  ],
  data_as_of: "2026-09-24T00:00:00Z",
  trace: { fallback: null },
};

test("requires both grounded and source-free cases before any request", async () => {
  let called = false;
  await assert.rejects(
    runIntegration({
      base: "http://localhost:3000",
      accounts: [],
      cases: [cases[0]],
      fetcher: () => {
        called = true;
      },
    }),
  );
  assert.equal(called, false);
  assert.throws(
    () => validateCases([cases[0], cases[0]]),
    /clarification or no-data/,
  );
});
test("rejects unverified facts, missing sources, dangling citations and timestamp mismatches", () => {
  verifyAnswer(grounded, cases[0]);
  for (const changed of [
    { answer: "invented fact [1]" },
    { sources: [] },
    { answer: "verified fact [2]" },
    { sources: [...grounded.sources, grounded.sources[0]] },
    { data_as_of: "2026-09-25T00:00:00Z" },
    { trace: { fallback: "retrieval_down" } },
  ])
    assert.throws(() => verifyAnswer({ ...grounded, ...changed }, cases[0]));
});
test("accepts a source-free clarification without inventing citations", () => {
  verifyAnswer(
    {
      ...grounded,
      answer: "Which team?",
      sources: [],
      route: "clarify",
      data_as_of: null,
    },
    cases[1],
  );
});

function fakeSystem({ leakHistory = false } = {}) {
  const calls = [],
    saved = new Map();
  let count = 0;
  const response = (value, status = 200, headers = {}) =>
    new Response(JSON.stringify(value), { status, headers });
  const fetcher = async (url, options) => {
    const path = url.pathname,
      user = options.headers.Cookie?.split("=")[1];
    calls.push({ path, method: options.method });
    if (path === "/health") return response({ status: "ok" });
    if (path === "/api/auth/login") {
      const { username } = JSON.parse(options.body);
      return response({ user: { username, role: "user" } }, 200, {
        "set-cookie": `access_token=${username}; HttpOnly`,
      });
    }
    if (path === "/api/auth/logout")
      return response({ ok: true }, 200, {
        "set-cookie": "access_token=; HttpOnly",
      });
    if (path === "/api/auth/me") return response({}, 401);
    if (path === "/api/chat") {
      count++;
      const answer = {
        ...grounded,
        session_id: `session-${count}`,
        message_id: `message-${count}`,
      };
      if (count === 2)
        Object.assign(answer, {
          answer: "Which team?",
          sources: [],
          route: "clarify",
          data_as_of: null,
        });
      saved.set(answer.session_id, { ...answer, rating: null });
      return response(answer, 200, { "x-request-id": answer.request_id });
    }
    if (path.startsWith("/api/history/")) {
      if (user === "b" && !leakHistory) return response({}, 404);
      const answer = saved.get(path.split("/").at(-1));
      return response({ messages: [{ ...answer, content: answer.answer }] });
    }
    if (path === "/api/sessions")
      return response({ sessions: user === "b" ? [] : [...saved.values()] });
    if (path === "/api/feedback") {
      const { message_id } = JSON.parse(options.body);
      [...saved.values()].find(
        (answer) => answer.message_id === message_id,
      ).rating = 1;
      return response({ ok: true });
    }
    if (path === "/api/admin/stats") return response({}, 403);
    if (path === "/api/football/standings") return response({ rows: [{}] });
    const match = {
      match_id: "match-1",
      home: { team_id: 1 },
      away: { team_id: 2 },
    };
    if (path === "/api/football/fixtures")
      return response({ matches: [match] });
    if (path === "/api/football/matches/match-1") return response(match);
    throw new Error(`Unexpected request ${path}`);
  };
  return { fetcher, calls };
}
const config = {
  base: "http://localhost:3000",
  accounts: [
    { username: "a", password: "test" },
    { username: "b", password: "test" },
  ],
  cases,
  log: () => {},
};
test("runs the HTTP checks and logs out both users without admin mutations", async () => {
  const system = fakeSystem();
  assert.equal(await runIntegration({ ...config, fetcher: system.fetcher }), 6);
  assert.equal(
    system.calls.filter((call) => call.path === "/api/auth/logout").length,
    2,
  );
  assert.ok(
    system.calls
      .filter((call) => call.path.startsWith("/api/admin"))
      .every((call) => call.method === "GET"),
  );
});
test("fails cross-account leakage and still logs out both accounts", async () => {
  const system = fakeSystem({ leakHistory: true });
  await assert.rejects(
    runIntegration({ ...config, fetcher: system.fetcher }),
    /unexpected HTTP status/,
  );
  assert.equal(
    system.calls.filter((call) => call.path === "/api/auth/logout").length,
    2,
  );
});
