import { afterEach, describe, expect, it } from "vitest";
import { mintApiAccessToken } from "./access-token";

describe("mintApiAccessToken", () => {
  const prev = process.env.AUTH_SECRET;

  afterEach(() => {
    if (prev === undefined) delete process.env.AUTH_SECRET;
    else process.env.AUTH_SECRET = prev;
  });

  it("mints an HS256 JWT with sub / iss / aud", async () => {
    process.env.AUTH_SECRET = "test-auth-secret-at-least-32-chars-long";
    const { token, expiresAt } = await mintApiAccessToken({
      userId: "00000000-0000-0000-0000-000000000099",
      email: "a@example.com",
    });
    expect(token.split(".")).toHaveLength(3);
    expect(Date.parse(expiresAt)).toBeGreaterThan(Date.now());

    const payload = JSON.parse(
      Buffer.from(token.split(".")[1]!, "base64url").toString("utf8"),
    ) as Record<string, unknown>;
    expect(payload.sub).toBe("00000000-0000-0000-0000-000000000099");
    expect(payload.iss).toBe("interviewbuddy");
    expect(payload.aud).toBe("interviewbuddy-api");
    expect(payload.email).toBe("a@example.com");
  });
});
