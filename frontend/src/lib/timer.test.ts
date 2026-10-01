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

  it("freezes when clockMs is provided (completed sessions)", () => {
    const ends = "2026-09-29T12:15:00Z";
    const completedAt = Date.parse("2026-09-29T12:06:00Z");
    const later = Date.parse("2026-09-29T12:10:00Z");
    expect(secondsRemaining(ends, later, completedAt)).toBe(540);
  });
});

describe("formatCountdown", () => {
  it("formats mm:ss", () => {
    expect(formatCountdown(125)).toBe("2:05");
    expect(formatCountdown(0)).toBe("0:00");
  });
});
