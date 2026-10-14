export type RateLimitResult =
  | { ok: true }
  | { ok: false; retryAfterSeconds: number };

export type RateLimitOptions = {
  limit: number;
  windowMs: number;
  /** Injectable clock for tests. */
  now?: () => number;
};

/** Fixed-window counter; fine for single-node Next.js. */
export class MemoryRateLimiter {
  private readonly limit: number;
  private readonly windowMs: number;
  private readonly now: () => number;
  private readonly hits = new Map<string, number[]>();

  constructor(opts: RateLimitOptions) {
    this.limit = opts.limit;
    this.windowMs = opts.windowMs;
    this.now = opts.now ?? Date.now;
  }

  check(key: string): RateLimitResult {
    const t = this.now();
    const cutoff = t - this.windowMs;
    const prev = (this.hits.get(key) ?? []).filter((ts) => ts > cutoff);
    if (prev.length >= this.limit) {
      const oldest = prev[0] ?? t;
      const retryAfterSeconds = Math.max(
        1,
        Math.ceil((oldest + this.windowMs - t) / 1000),
      );
      this.hits.set(key, prev);
      return { ok: false, retryAfterSeconds };
    }
    prev.push(t);
    this.hits.set(key, prev);
    return { ok: true };
  }
}

/** Shared limiters for auth HTTP surfaces. */
export const signupLimiter = new MemoryRateLimiter({
  limit: 10,
  windowMs: 15 * 60_000,
});
export const loginLimiter = new MemoryRateLimiter({
  limit: 20,
  windowMs: 15 * 60_000,
});
export const accessTokenLimiter = new MemoryRateLimiter({
  limit: 60,
  windowMs: 60_000,
});
