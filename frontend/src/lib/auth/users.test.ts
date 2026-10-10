import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  createUser,
  findUserByEmail,
  resetUsersStoreForTests,
  verifyUserCredentials,
} from "./users";

describe("users store", () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "auth-users-"));
    process.env.AUTH_USERS_PATH = path.join(dir, "users.json");
    resetUsersStoreForTests();
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
    delete process.env.AUTH_USERS_PATH;
    resetUsersStoreForTests();
  });

  it("creates a user with a hashed password", async () => {
    const user = await createUser({
      email: "Ada@Example.com",
      password: "securepass",
      name: "Ada",
    });

    expect(user.email).toBe("ada@example.com");
    expect(user.name).toBe("Ada");
    expect(user.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );
    expect(user).not.toHaveProperty("passwordHash");

    const stored = await findUserByEmail("ada@example.com");
    expect(stored?.passwordHash).toBeTruthy();
    expect(stored?.passwordHash).not.toBe("securepass");
  });

  it("rejects duplicate email", async () => {
    await createUser({ email: "dup@example.com", password: "securepass" });
    await expect(
      createUser({ email: "dup@example.com", password: "securepass" }),
    ).rejects.toMatchObject({ code: "EMAIL_TAKEN" });
  });

  it("verifies credentials for an existing user", async () => {
    await createUser({ email: "login@example.com", password: "securepass" });
    const ok = await verifyUserCredentials("login@example.com", "securepass");
    expect(ok?.email).toBe("login@example.com");
    await expect(
      verifyUserCredentials("login@example.com", "nope-nope"),
    ).resolves.toBeNull();
  });
});
