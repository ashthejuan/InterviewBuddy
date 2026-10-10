import { describe, expect, it } from "vitest";
import { SESSION_MAX_AGE_SECONDS } from "./session-config";

describe("session cookie TTL", () => {
  it("is six hours in seconds", () => {
    expect(SESSION_MAX_AGE_SECONDS).toBe(6 * 60 * 60);
  });
});
