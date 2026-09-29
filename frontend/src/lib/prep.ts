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
