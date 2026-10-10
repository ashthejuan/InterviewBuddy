import { describe, expect, it } from "vitest";
import { hashPassword, verifyPassword, validatePassword } from "./password";

describe("validatePassword", () => {
  it("rejects passwords shorter than 8 characters", () => {
    expect(validatePassword("short")).toEqual({
      ok: false,
      error: "Password must be at least 8 characters",
    });
  });

  it("accepts passwords with at least 8 characters", () => {
    expect(validatePassword("longenough")).toEqual({ ok: true });
  });
});

describe("hashPassword / verifyPassword", () => {
  it("verifies a matching password and rejects a wrong one", async () => {
    const hash = await hashPassword("correct-horse");
    await expect(verifyPassword("correct-horse", hash)).resolves.toBe(true);
    await expect(verifyPassword("wrong-password", hash)).resolves.toBe(false);
  });
});
