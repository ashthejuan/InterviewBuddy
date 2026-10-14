import { randomUUID } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  createUser,
  findUserByEmail,
  resetUsersStoreForTests,
  verifyUserCredentials,
} from "./users";

/**
 * Uses the same Postgres as docker compose (DATABASE_URL).
 * Each test uses a unique email and deletes the row afterward.
 */
describe("users store (Postgres password_hash)", () => {
  const emails: string[] = [];

  beforeEach(async () => {
    if (!process.env.DATABASE_URL) {
      process.env.DATABASE_URL =
        "postgresql://interviewbuddy:interviewbuddy@localhost:5432/interviewbuddy";
    }
    await resetUsersStoreForTests();
  });

  afterEach(async () => {
    const { deleteUsersByEmailsForTests } = await import("./users");
    await deleteUsersByEmailsForTests(emails.splice(0));
    resetUsersStoreForTests();
  });

  it("creates a user with a hashed password in Postgres", async () => {
    const email = `ada-${randomUUID()}@example.com`;
    emails.push(email);

    const user = await createUser({
      email: email.toUpperCase().replace("ada", "Ada"),
      password: "securepass",
      name: "Ada",
    });

    expect(user.email).toBe(email.toLowerCase());
    expect(user.name).toBe("Ada");
    expect(user.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );
    expect(user).not.toHaveProperty("passwordHash");

    const stored = await findUserByEmail(email);
    expect(stored?.passwordHash).toBeTruthy();
    expect(stored?.passwordHash).not.toBe("securepass");
    expect(stored?.passwordHash.startsWith("$2")).toBe(true);
  });

  it("rejects duplicate email", async () => {
    const email = `dup-${randomUUID()}@example.com`;
    emails.push(email);
    await createUser({ email, password: "securepass" });
    await expect(
      createUser({ email, password: "securepass" }),
    ).rejects.toMatchObject({ code: "EMAIL_TAKEN" });
  });

  it("verifies credentials for an existing user", async () => {
    const email = `login-${randomUUID()}@example.com`;
    emails.push(email);
    await createUser({ email, password: "securepass" });
    const ok = await verifyUserCredentials(email, "securepass");
    expect(ok?.email).toBe(email);
    await expect(
      verifyUserCredentials(email, "nope-nope"),
    ).resolves.toBeNull();
  });
});
