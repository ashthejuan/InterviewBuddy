import { describe, expect, it, vi } from "vitest";
import { shouldRetryStatus, withRetries } from "./retry";

describe("shouldRetryStatus", () => {
  it("retries 429 and 5xx only", () => {
    expect(shouldRetryStatus(429)).toBe(true);
    expect(shouldRetryStatus(503)).toBe(true);
    expect(shouldRetryStatus(400)).toBe(false);
    expect(shouldRetryStatus(401)).toBe(false);
    expect(shouldRetryStatus(404)).toBe(false);
  });
});

describe("withRetries", () => {
  it("retries then succeeds", async () => {
    let n = 0;
    const result = await withRetries(
      async () => {
        n += 1;
        if (n < 3) {
          const err = Object.assign(new Error("busy"), { status: 429 });
          throw err;
        }
        return "ok";
      },
      { maxAttempts: 3, baseDelayMs: 1, jitterMs: 0 },
    );
    expect(result).toBe("ok");
    expect(n).toBe(3);
  });

  it("gives up after maxAttempts", async () => {
    await expect(
      withRetries(
        async () => {
          throw Object.assign(new Error("nope"), { status: 503 });
        },
        { maxAttempts: 2, baseDelayMs: 1, jitterMs: 0 },
      ),
    ).rejects.toMatchObject({ status: 503 });
  });
});
