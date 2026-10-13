import { describe, expect, it } from "vitest";
import { ApiError, type TurnOut } from "./api";
import {
  canJoinVoice,
  canSubmitVoiceAnswer,
  describeVoiceError,
  displayTurnText,
  interviewerStatus,
  isVoiceActive,
  phaseFromConnectionState,
  upsertHeardSegment,
  voicePhaseLabel,
  type HeardSegment,
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

describe("upsertHeardSegment", () => {
  it("replaces interim text in place, then finalizes the same segment", () => {
    let list = upsertHeardSegment([], { id: "a", text: "I built", final: false });
    list = upsertHeardSegment(list, { id: "a", text: "I built the API", final: false });
    expect(list).toEqual([{ id: "a", text: "I built the API", final: false }]);
    list = upsertHeardSegment(list, { id: "a", text: "I built the API.", final: true });
    expect(list).toEqual([{ id: "a", text: "I built the API.", final: true }]);
  });

  it("appends new segments and keeps only the most recent", () => {
    let list: HeardSegment[] = [];
    for (const id of ["1", "2", "3", "4"]) {
      list = upsertHeardSegment(list, { id, text: id, final: true }, 3);
    }
    expect(list.map((s) => s.id)).toEqual(["2", "3", "4"]);
  });

  it("ignores blank interim text", () => {
    expect(upsertHeardSegment([], { id: "a", text: "  ", final: false })).toEqual([]);
  });
});

describe("interviewerStatus", () => {
  it("warns when the agent never joins", () => {
    expect(interviewerStatus({ joined: false, state: null, waitedTooLong: false })).toMatch(
      /waiting/i,
    );
    expect(interviewerStatus({ joined: false, state: null, waitedTooLong: true })).toMatch(
      /hasn't joined/i,
    );
  });

  it("walks question → answer → evaluating once joined", () => {
    const base = { joined: true, waitedTooLong: false };
    expect(interviewerStatus({ ...base, state: "speaking" })).toMatch(/asking/i);
    expect(interviewerStatus({ ...base, state: "listening" })).toMatch(/submit answer/i);
    expect(interviewerStatus({ ...base, state: "listening", awaitingReply: true })).toMatch(
      /evaluating/i,
    );
    expect(interviewerStatus({ ...base, state: "thinking" })).toMatch(/evaluating/i);
    expect(interviewerStatus({ ...base, state: null })).toMatch(/getting ready/i);
  });
});

describe("canSubmitVoiceAnswer", () => {
  const ready = {
    joined: true,
    state: "listening",
    awaitingReply: false,
    submitting: false,
    heard: [{ id: "a", text: "I built it", final: true }],
  };

  it("allows submit while the agent waits and speech was heard", () => {
    expect(canSubmitVoiceAnswer(ready)).toBe(true);
  });

  it("blocks submit while asking, evaluating, submitting, or with nothing heard", () => {
    expect(canSubmitVoiceAnswer({ ...ready, state: "speaking" })).toBe(false);
    expect(canSubmitVoiceAnswer({ ...ready, awaitingReply: true })).toBe(false);
    expect(canSubmitVoiceAnswer({ ...ready, submitting: true })).toBe(false);
    expect(canSubmitVoiceAnswer({ ...ready, heard: [] })).toBe(false);
    expect(canSubmitVoiceAnswer({ ...ready, joined: false })).toBe(false);
  });
});
