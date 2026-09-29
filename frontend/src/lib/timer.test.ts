import { describe, expect, it } from "vitest";
import { formatCountdown, secondsRemaining } from "./timer";

describe("secondsRemaining", () => {
  it("returns positive seconds until ends_at", () => {
    const now = Date.parse("2026-09-29T12:00:00Z");
    expect(secondsRemaining("2026-09-29T12:05:00Z", now)).toBe(300);
  });

  it("clamps at zero when expired", () => {
    const now = Date.parse("2026-09-29T12:10:00Z");
    expect(secondsRemaining("2026-09-29T12:05:00Z", now)).toBe(0);
  });
});

describe("formatCountdown", () => {
  it("formats mm:ss", () => {
    expect(formatCountdown(125)).toBe("2:05");
    expect(formatCountdown(0)).toBe("0:00");
  });
});
