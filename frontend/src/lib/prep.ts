/** Session prep helpers — start gate + status copy. */

export type SessionStatus =
  | "preparing"
  | "ready"
  | "live"
  | "completed"
  | "failed";

export function canStartInterview(status: SessionStatus): boolean {
  return status === "ready";
}

export function prepLabel(status: SessionStatus): string {
  switch (status) {
    case "preparing":
      return "Preparing documents…";
    case "ready":
      return "Ready to start";
    case "failed":
      return "Prep failed";
    case "live":
      return "Interview live";
    case "completed":
      return "Interview completed";
  }
}

/** Show Prepare / Re-prepare only before first prep or after failure. */
export function showPrepareAction(status: SessionStatus | null): boolean {
  return status === null || status === "failed";
}

export function prepareActionLabel(status: SessionStatus | null): string {
  return status === "failed" ? "Re-prepare" : "Prepare session";
}

/** True while uploads/create are in flight or backend is still preparing. */
export function isPrepInFlight(
  status: SessionStatus | null,
  busy: boolean,
): boolean {
  return busy || status === "preparing";
}
