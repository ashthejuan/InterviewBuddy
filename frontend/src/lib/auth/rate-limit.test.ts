import { describe, expect, it } from "vitest";
import { MemoryRateLimiter } from "./rate-limit";

describe("MemoryRateLimiter", () => {
  it("allows requests under the limit", () => {
    const limiter = new MemoryRateLimiter({ limit: 3, windowMs: 60_000 });
    expect(limiter.check("a").ok).toBe(true);
    expect(limiter.check("a").ok).toBe(true);
    expect(limiter.check("a").ok).toBe(true);
  });

  it("blocks when over the limit and reports retryAfterSeconds", () => {
    const limiter = new MemoryRateLimiter({ limit: 2, windowMs: 60_000 });
    limiter.check("b");
    limiter.check("b");
    const blocked = limiter.check("b");
    expect(blocked.ok).toBe(false);
    if (!blocked.ok) {
      expect(blocked.retryAfterSeconds).toBeGreaterThan(0);
    }
  });

  it("isolates keys", () => {
    const limiter = new MemoryRateLimiter({ limit: 1, windowMs: 60_000 });
    expect(limiter.check("x").ok).toBe(true);
    expect(limiter.check("x").ok).toBe(false);
    expect(limiter.check("y").ok).toBe(true);
  });
});
