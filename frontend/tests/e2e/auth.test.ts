/**
 * Auth.js credentials e2e: HTTP surface for signup + login against Postgres.
 */
import { randomUUID } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("auth e2e — POST /signup and POST /login", () => {
  const emails: string[] = [];

  beforeEach(() => {
    process.env.AUTH_SECRET = "test-auth-secret-at-least-32-chars-long";
    process.env.AUTH_URL = "http://localhost:3000";
    if (!process.env.DATABASE_URL) {
      process.env.DATABASE_URL =
        "postgresql://interviewbuddy:interviewbuddy@localhost:5432/interviewbuddy";
    }
  });

  afterEach(async () => {
    const { deleteUsersByEmailsForTests, resetUsersStoreForTests } =
      await import("@/lib/auth/users");
    await deleteUsersByEmailsForTests(emails.splice(0));
    await resetUsersStoreForTests();
    vi.resetModules();
  });

  async function postSignup(body: unknown) {
    const { POST } = await import("@/app/api/signup/route");
    return POST(
      new Request("http://localhost:3000/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
  }

  async function postLogin(body: unknown) {
    const { POST } = await import("@/app/api/login/route");
    return POST(
      new Request("http://localhost:3000/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
  }

  it("signs up then logs in with email and password", async () => {
    const email = `e2e-${randomUUID()}@example.com`;
    emails.push(email);
    const password = "securepass";

    const signupRes = await postSignup({
      email,
      password,
      name: "E2E User",
    });
    expect(signupRes.status).toBe(201);
    const created = await signupRes.json();
    expect(created).toMatchObject({
      email,
      name: "E2E User",
    });
    expect(created.id).toBeTruthy();
    expect(created).not.toHaveProperty("passwordHash");

    const loginRes = await postLogin({ email, password });
    expect(loginRes.status).toBe(200);
    const session = await loginRes.json();
    expect(session).toMatchObject({
      ok: true,
      user: { id: created.id, email, name: "E2E User" },
    });
  });

  it("rejects signup with a weak password", async () => {
    const res = await postSignup({
      email: `weak-${randomUUID()}@example.com`,
      password: "short",
    });
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/at least 8/i);
  });

  it("rejects login with wrong password", async () => {
    const email = `bad-${randomUUID()}@example.com`;
    emails.push(email);
    await postSignup({ email, password: "securepass" });

    const res = await postLogin({
      email,
      password: "wrong-pass",
    });
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.error).toMatch(/invalid/i);
  });

  it("rejects duplicate signup", async () => {
    const email = `dup-${randomUUID()}@example.com`;
    emails.push(email);
    const payload = { email, password: "securepass" };
    const first = await postSignup(payload);
    expect(first.status).toBe(201);

    const second = await postSignup(payload);
    expect(second.status).toBe(409);
  });
});
