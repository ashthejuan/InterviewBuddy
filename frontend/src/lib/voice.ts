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

/** User turns show the lexicon-corrected text the grill actually used. */
export function displayTurnText(turn: TurnOut): string {
  if (turn.role === "user" && turn.normalized_text) return turn.normalized_text;
  return turn.raw_text;
}
