/**
 * Auth.js credentials e2e: HTTP surface for signup + login.
 * Uses route handlers (same as production) against an isolated user store.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("auth e2e — POST /signup and POST /login", () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "auth-e2e-"));
    process.env.AUTH_USERS_PATH = path.join(dir, "users.json");
    process.env.AUTH_SECRET = "test-auth-secret-at-least-32-chars-long";
    process.env.AUTH_URL = "http://localhost:3000";
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
    delete process.env.AUTH_USERS_PATH;
    // Reset module state between tests (store path)
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
    const { resetUsersStoreForTests } = await import("@/lib/auth/users");
    resetUsersStoreForTests();

    const email = "e2e@example.com";
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
    const { resetUsersStoreForTests } = await import("@/lib/auth/users");
    resetUsersStoreForTests();

    const res = await postSignup({
      email: "weak@example.com",
      password: "short",
    });
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/at least 8/i);
  });

  it("rejects login with wrong password", async () => {
    const { resetUsersStoreForTests } = await import("@/lib/auth/users");
    resetUsersStoreForTests();

    await postSignup({ email: "bad@example.com", password: "securepass" });

    const res = await postLogin({
      email: "bad@example.com",
      password: "wrong-pass",
    });
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.error).toMatch(/invalid/i);
  });

  it("rejects duplicate signup", async () => {
    const { resetUsersStoreForTests } = await import("@/lib/auth/users");
    resetUsersStoreForTests();

    const payload = {
      email: "dup@example.com",
      password: "securepass",
    };
    const first = await postSignup(payload);
    expect(first.status).toBe(201);

    const second = await postSignup(payload);
    expect(second.status).toBe(409);
  });
});
