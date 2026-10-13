import { ApiError, type SessionStatus, type TurnOut } from "@/lib/api";

export type VoicePhase =
  | "idle"
  | "requesting_mic"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "error";

/** Map livekit-client `ConnectionState` values onto UI phases. */
export function phaseFromConnectionState(state: string): VoicePhase {
  switch (state) {
    case "connecting":
      return "connecting";
    case "connected":
      return "connected";
    case "reconnecting":
    case "signalReconnecting":
      return "reconnecting";
    case "disconnected":
      return "disconnected";
    default:
      return "idle";
  }
}

const LABELS: Record<VoicePhase, string> = {
  idle: "Voice off",
  requesting_mic: "Waiting for microphone…",
  connecting: "Connecting…",
  connected: "Voice live",
  reconnecting: "Reconnecting…",
  disconnected: "Voice ended",
  error: "Voice error",
};

export function voicePhaseLabel(phase: VoicePhase): string {
  return LABELS[phase];
}

export function isVoiceActive(phase: VoicePhase): boolean {
  return (
    phase === "requesting_mic" ||
    phase === "connecting" ||
    phase === "connected" ||
    phase === "reconnecting"
  );
}

export function canJoinVoice(opts: {
  sessionStatus: SessionStatus | undefined;
  voiceEnabled: boolean;
  phase: VoicePhase;
}): boolean {
  return (
    opts.voiceEnabled &&
    opts.sessionStatus === "live" &&
    (opts.phase === "idle" || opts.phase === "error")
  );
}

export const AGENT_DROPPED_MESSAGE =
  "The voice interviewer disconnected. Keep going by typing, or rejoin voice.";

export function describeVoiceError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 503) return "Voice isn't configured on the server yet.";
    if (err.status === 409) return "Start the interview before joining voice.";
    return err.message;
  }
  const name =
    typeof err === "object" && err !== null && "name" in err
      ? String((err as { name: unknown }).name)
      : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone permission was blocked. Allow mic access in your browser and try again.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "No microphone found. Plug one in or pick another input device.";
  }
  if (name === "NotReadableError") {
    return "Your microphone is in use by another app.";
  }
  if (err instanceof Error && err.message) return err.message;
  return "Voice connection failed.";
}

/** LiveKit agents publish STT on this text-stream topic (one stream per interim/final). */
export const TRANSCRIPTION_TOPIC = "lk.transcription";
export const ATTR_SEGMENT_ID = "lk.segment_id";
export const ATTR_TRANSCRIPTION_FINAL = "lk.transcription_final";
export const ATTR_AGENT_STATE = "lk.agent.state";
export const AGENT_JOIN_TIMEOUT_MS = 10_000;
/** RPC methods registered by `backend/agent/worker.py`. */
export const RPC_SUBMIT_ANSWER = "submit_answer";
export const RPC_CLEAR_ANSWER = "clear_answer";
/** Worker waits up to 8 s for the final STT transcript before replying. */
export const SUBMIT_RPC_TIMEOUT_MS = 15_000;
export const NOTHING_HEARD_MESSAGE =
  "The interviewer didn't catch anything. Speak your answer, then submit again.";

export type HeardSegment = { id: string; text: string; final: boolean };

/** Interim results reuse the segment id, so replace in place; keep the last `max`. */
export function upsertHeardSegment(
  list: HeardSegment[],
  seg: HeardSegment,
  max = 50,
): HeardSegment[] {
  const text = seg.text.trim();
  const idx = list.findIndex((s) => s.id === seg.id);
  if (!text) return idx === -1 ? list : list.filter((_, i) => i !== idx);
  const next = { ...seg, text };
  const out = idx === -1 ? [...list, next] : list.map((s, i) => (i === idx ? next : s));
  return out.slice(-max);
}

export function interviewerStatus(opts: {
  joined: boolean;
  state: string | null;
  waitedTooLong: boolean;
  awaitingReply?: boolean;
}): string {
  if (!opts.joined) {
    return opts.waitedTooLong
      ? "The interviewer hasn't joined. Is the voice agent worker running?"
      : "Waiting for the interviewer to join…";
  }
  if (opts.state === "speaking") return "Interviewer is asking the question…";
  if (opts.awaitingReply || opts.state === "thinking") {
    return "Evaluating your answer and preparing the next question…";
  }
  if (opts.state === "listening") {
    return "Your turn — answer out loud, then press Submit answer.";
  }
  return "Interviewer is getting ready…";
}

/** Submit only when the agent is waiting on the candidate and something was heard. */
export function canSubmitVoiceAnswer(opts: {
  joined: boolean;
  state: string | null;
  awaitingReply: boolean;
  submitting: boolean;
  heard: HeardSegment[];
}): boolean {
  return (
    opts.joined &&
    opts.state === "listening" &&
    !opts.awaitingReply &&
    !opts.submitting &&
    opts.heard.some((s) => s.text.trim())
  );
}

/** User turns show the lexicon-corrected text the grill actually used. */
export function displayTurnText(turn: TurnOut): string {
  if (turn.role === "user" && turn.normalized_text) return turn.normalized_text;
  return turn.raw_text;
}
