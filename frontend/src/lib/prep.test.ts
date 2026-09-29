import { describe, expect, it } from "vitest";
import {
  canStartInterview,
  prepLabel,
  type SessionStatus,
} from "./prep";

describe("canStartInterview", () => {
  it("allows start only when session is ready", () => {
    expect(canStartInterview("ready")).toBe(true);
  });

  it.each<[SessionStatus]>([
    ["preparing"],
    ["failed"],
    ["live"],
    ["completed"],
  ])("blocks start when status is %s", (status) => {
    expect(canStartInterview(status)).toBe(false);
  });
});

describe("prepLabel", () => {
  it("explains preparing while docs are still parsing", () => {
    expect(prepLabel("preparing")).toMatch(/preparing/i);
  });

  it("signals ready to start", () => {
    expect(prepLabel("ready")).toMatch(/ready/i);
  });

  it("surfaces failed prep", () => {
    expect(prepLabel("failed")).toMatch(/failed/i);
  });
});
