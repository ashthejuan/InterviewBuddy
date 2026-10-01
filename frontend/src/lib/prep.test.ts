import { describe, expect, it } from "vitest";
import {
  canStartInterview,
  isPrepInFlight,
  prepareActionLabel,
  prepLabel,
  showPrepareAction,
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

describe("showPrepareAction", () => {
  it("shows prepare before any session exists", () => {
    expect(showPrepareAction(null)).toBe(true);
  });

  it("shows re-prepare only after prep failed", () => {
    expect(showPrepareAction("failed")).toBe(true);
  });

  it.each<[SessionStatus]>([
    ["preparing"],
    ["ready"],
    ["live"],
    ["completed"],
  ])("hides prepare action when status is %s", (status) => {
    expect(showPrepareAction(status)).toBe(false);
  });
});

describe("prepareActionLabel", () => {
  it("labels first run as prepare session", () => {
    expect(prepareActionLabel(null)).toBe("Prepare session");
  });

  it("labels retry after failure as re-prepare", () => {
    expect(prepareActionLabel("failed")).toBe("Re-prepare");
  });
});

describe("isPrepInFlight", () => {
  it("is true while the prepare request is busy", () => {
    expect(isPrepInFlight(null, true)).toBe(true);
  });

  it("is true while session status is preparing", () => {
    expect(isPrepInFlight("preparing", false)).toBe(true);
  });

  it("is false when idle with no session", () => {
    expect(isPrepInFlight(null, false)).toBe(false);
  });

  it.each<[SessionStatus]>(["ready", "failed", "live", "completed"])(
    "is false when idle and status is %s",
    (status) => {
      expect(isPrepInFlight(status, false)).toBe(false);
    },
  );
});
