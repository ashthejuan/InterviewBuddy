export type Retryable = { status?: number };

export function shouldRetryStatus(status: number): boolean {
  return status === 429 || status >= 500;
}

export type RetryOptions = {
  maxAttempts?: number;
  baseDelayMs?: number;
  jitterMs?: number;
  sleep?: (ms: number) => Promise<void>;
};

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function withRetries<T>(
  fn: (attempt: number) => Promise<T>,
  opts: RetryOptions = {},
): Promise<T> {
  const maxAttempts = opts.maxAttempts ?? 3;
  const baseDelayMs = opts.baseDelayMs ?? 400;
  const jitterMs = opts.jitterMs ?? 200;
  const sleep = opts.sleep ?? defaultSleep;

  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn(attempt);
    } catch (err) {
      lastError = err;
      const status =
        err && typeof err === "object" && "status" in err
          ? Number((err as Retryable).status)
          : NaN;
      const retryable = Number.isFinite(status) && shouldRetryStatus(status);
      if (!retryable || attempt === maxAttempts) {
        throw err;
      }
      const delay =
        baseDelayMs * 2 ** (attempt - 1) +
        Math.floor(Math.random() * (jitterMs + 1));
      await sleep(delay);
    }
  }
  throw lastError;
}

export function userMessageForStatus(status: number, fallback: string): string {
  if (status === 429) {
    return "Too many requests — wait a moment and try again.";
  }
  if (status >= 500) {
    return "Server temporarily unavailable — retrying may help.";
  }
  return fallback;
}
