/** Session timer helpers for the live grill UI. */

export function secondsRemaining(
  endsAt: string | null,
  nowMs: number = Date.now(),
  frozenAtMs?: number | null,
): number {
  if (!endsAt) return 0;
  const end = Date.parse(endsAt);
  if (Number.isNaN(end)) return 0;
  const clock = frozenAtMs ?? nowMs;
  return Math.max(0, Math.floor((end - clock) / 1000));
}

export function formatCountdown(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}
