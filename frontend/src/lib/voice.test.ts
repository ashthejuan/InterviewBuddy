import { describe, expect, it } from "vitest";
import { ApiError, type TurnOut } from "./api";
import {
  canJoinVoice,
  describeVoiceError,
  displayTurnText,
  isVoiceActive,
  phaseFromConnectionState,
  voicePhaseLabel,
} from "./voice";

describe("phaseFromConnectionState", () => {
  it("maps livekit connection states", () => {
    expect(phaseFromConnectionState("connecting")).toBe("connecting");
    expect(phaseFromConnectionState("connected")).toBe("connected");
    expect(phaseFromConnectionState("reconnecting")).toBe("reconnecting");
    expect(phaseFromConnectionState("signalReconnecting")).toBe("reconnecting");
    expect(phaseFromConnectionState("disconnected")).toBe("disconnected");
    expect(phaseFromConnectionState("weird")).toBe("idle");
  });

  it("labels every phase", () => {
    expect(voicePhaseLabel("connected")).toBe("Voice live");
    expect(voicePhaseLabel("requesting_mic")).toMatch(/microphone/i);
  });
});

describe("isVoiceActive", () => {
  it("is true while mic/connecting/connected/reconnecting", () => {
    expect(isVoiceActive("requesting_mic")).toBe(true);
    expect(isVoiceActive("connecting")).toBe(true);
    expect(isVoiceActive("connected")).toBe(true);
    expect(isVoiceActive("reconnecting")).toBe(true);
    expect(isVoiceActive("idle")).toBe(false);
    expect(isVoiceActive("disconnected")).toBe(false);
    expect(isVoiceActive("error")).toBe(false);
  });
});

describe("canJoinVoice", () => {
  it("requires a live session with voice enabled", () => {
    expect(canJoinVoice({ sessionStatus: "live", voiceEnabled: true, phase: "idle" })).toBe(true);
    expect(canJoinVoice({ sessionStatus: "live", voiceEnabled: true, phase: "error" })).toBe(true);
    expect(canJoinVoice({ sessionStatus: "ready", voiceEnabled: true, phase: "idle" })).toBe(false);
    expect(canJoinVoice({ sessionStatus: "live", voiceEnabled: false, phase: "idle" })).toBe(false);
    expect(
      canJoinVoice({ sessionStatus: "live", voiceEnabled: true, phase: "connected" }),
    ).toBe(false);
    expect(canJoinVoice({ sessionStatus: undefined, voiceEnabled: true, phase: "idle" })).toBe(
      false,
    );
  });
});

describe("describeVoiceError", () => {
  it("explains mic permission and device failures", () => {
    expect(describeVoiceError({ name: "NotAllowedError" })).toMatch(/permission/i);
    expect(describeVoiceError({ name: "NotFoundError" })).toMatch(/no microphone/i);
    expect(describeVoiceError({ name: "NotReadableError" })).toMatch(/in use/i);
  });

  it("maps API errors", () => {
    expect(describeVoiceError(new ApiError(503, "x"))).toMatch(/configured/i);
    expect(describeVoiceError(new ApiError(409, "x"))).toMatch(/start/i);
    expect(describeVoiceError(new ApiError(500, "boom"))).toBe("boom");
  });

  it("falls back to message or a generic line", () => {
    expect(describeVoiceError(new Error("socket closed"))).toBe("socket closed");
    expect(describeVoiceError(42)).toBe("Voice connection failed.");
  });
});

describe("displayTurnText", () => {
  const base: TurnOut = {
    id: "t",
    role: "user",
    raw_text: "fast api",
    normalized_text: "FastAPI",
    topic_id: null,
    frontier_node_id: null,
    created_at: "",
  };

  it("shows normalized text for user turns", () => {
    expect(displayTurnText(base)).toBe("FastAPI");
    expect(displayTurnText({ ...base, normalized_text: null })).toBe("fast api");
  });

  it("shows raw text for agent turns", () => {
    expect(displayTurnText({ ...base, role: "agent" })).toBe("fast api");
  });
});
