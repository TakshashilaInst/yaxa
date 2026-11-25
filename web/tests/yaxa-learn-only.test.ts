import test from "node:test";
import assert from "node:assert/strict";

// Yaxa: only admins use DeepTutor's own pages; everyone else is kept on /learn.
import { isLearnOnlyPath, tokenRole } from "../lib/proxy-policy";

function jwt(payload: Record<string, unknown>): string {
  const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${b64({ alg: "HS256" })}.${b64(payload)}.sig`;
}

test("tokenRole reads the role claim, and is null for missing or broken tokens", () => {
  assert.equal(tokenRole(jwt({ sub: "a", role: "admin" })), "admin");
  assert.equal(tokenRole(jwt({ sub: "s", role: "user" })), "user");
  assert.equal(tokenRole(jwt({ sub: "s" })), null);
  assert.equal(tokenRole(undefined), null);
  assert.equal(tokenRole("not-a-jwt"), null);
});

test("students may use Yaxa Learn, login and assets", () => {
  for (const p of ["/learn", "/learn/module/GCPP-ER1", "/learn/chat/new", "/login", "/register", "/handoff", "/logo.png"]) {
    assert.equal(isLearnOnlyPath(p), true, p);
  }
});

test("DeepTutor's own pages are not for students", () => {
  for (const p of ["/chat", "/chat/abc", "/settings", "/admin/users", "/knowledge", "/learning/mastery/x", "/", "/learner"]) {
    assert.equal(isLearnOnlyPath(p), false, p);
  }
});
