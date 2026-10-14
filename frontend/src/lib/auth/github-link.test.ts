import { randomUUID } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createUser, deleteUsersByEmailsForTests, resetUsersStoreForTests } from "./users";
import { linkOrCreateGithubUser } from "./github-link";

describe("linkOrCreateGithubUser", () => {
  const emails: string[] = [];

  beforeEach(async () => {
    if (!process.env.DATABASE_URL) {
      process.env.DATABASE_URL =
        "postgresql://interviewbuddy:interviewbuddy@localhost:5432/interviewbuddy";
    }
    await resetUsersStoreForTests();
  });

  afterEach(async () => {
    await deleteUsersByEmailsForTests(emails.splice(0));
    await resetUsersStoreForTests();
  });

  it("creates an OAuth-only user when email is new", async () => {
    const email = `gh-new-${randomUUID()}@example.com`;
    emails.push(email);
    const user = await linkOrCreateGithubUser({
      githubId: `gh-${randomUUID()}`,
      email,
      name: "Octo",
    });
    expect(user.email).toBe(email);
    expect(user.name).toBe("Octo");
    expect(user.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );
  });

  it("links GitHub to an existing password account by email", async () => {
    const email = `gh-link-${randomUUID()}@example.com`;
    emails.push(email);
    const existing = await createUser({
      email,
      password: "securepass",
      name: "Ada",
    });
    const githubId = `gh-${randomUUID()}`;
    const linked = await linkOrCreateGithubUser({
      githubId,
      email,
      name: "Ada Lovelace",
    });
    expect(linked.id).toBe(existing.id);
    expect(linked.email).toBe(email);

    // Same GitHub id again → same user
    const again = await linkOrCreateGithubUser({
      githubId,
      email: `other-${randomUUID()}@example.com`,
      name: "Ignored",
    });
    emails.push(again.email);
    expect(again.id).toBe(existing.id);
  });

  it("rejects missing email", async () => {
    await expect(
      linkOrCreateGithubUser({
        githubId: `gh-${randomUUID()}`,
        email: "",
        name: null,
      }),
    ).rejects.toMatchObject({ code: "EMAIL_REQUIRED" });
  });
});
