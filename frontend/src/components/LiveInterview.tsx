"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  ApiError,
  answerSession,
  endSession,
  getSession,
  getSessionTopics,
  getSessionTurns,
  getVoiceStatus,
  type SessionOut,
  type TopicOut,
  type TurnOut,
} from "@/lib/api";
import { formatCountdown, secondsRemaining } from "@/lib/timer";
import { useVoiceRoom } from "@/lib/useVoiceRoom";
import {
  canJoinVoice,
  canSubmitVoiceAnswer,
  displayTurnText,
  interviewerStatus,
  isVoiceActive,
  voicePhaseLabel,
} from "@/lib/voice";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { SessionResults } from "@/components/SessionResults";

export function LiveInterview({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<SessionOut | null>(null);
  const [topics, setTopics] = useState<TopicOut[]>([]);
  const [turns, setTurns] = useState<TurnOut[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [frozenAtMs, setFrozenAtMs] = useState<number | null>(null);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const voice = useVoiceRoom(sessionId);
  const voiceActive = isVoiceActive(voice.phase);
  const leaveVoice = voice.leave;

  const refresh = useCallback(async () => {
    const [s, t, tr] = await Promise.all([
      getSession(sessionId),
      getSessionTopics(sessionId),
      getSessionTurns(sessionId),
    ]);
    setSession(s);
    setTopics(t);
    setTurns(tr);
  }, [sessionId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load session");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  useEffect(() => {
    if (session?.status === "completed") {
      setFrozenAtMs((prev) => prev ?? Date.now());
      return;
    }
    setFrozenAtMs(null);
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [session?.status]);

  useEffect(() => {
    getVoiceStatus()
      .then((s) => setVoiceEnabled(s.enabled))
      .catch(() => setVoiceEnabled(false));
  }, []);

  // The agent writes turns server-side; poll while the call is up.
  useEffect(() => {
    if (!voiceActive) return;
    const id = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(id);
  }, [voiceActive, refresh]);

  const remaining = secondsRemaining(session?.ends_at ?? null, nowMs, frozenAtMs);
  const activeTopic = topics.find((t) => t.status === "active") ?? null;
  const completed = session?.status === "completed";
  const live = session?.status === "live";
  const voiceTalking = voice.phase === "connected" || voice.phase === "reconnecting";

  useEffect(() => {
    if (completed && voiceActive) void leaveVoice();
  }, [completed, voiceActive, leaveVoice]);

  // A dropped call wraps the session server-side; give the agent a moment, then resync.
  useEffect(() => {
    if (voice.phase !== "disconnected") return;
    const id = window.setTimeout(() => {
      refresh().catch(() => undefined);
    }, 1500);
    return () => window.clearTimeout(id);
  }, [voice.phase, refresh]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!live || !draft.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const out = await answerSession(sessionId, draft.trim());
      setSession(out.session);
      setDraft("");
      const [t, tr] = await Promise.all([
        getSessionTopics(sessionId),
        getSessionTurns(sessionId),
      ]);
      setTopics(t);
      setTurns(tr);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Answer failed");
    } finally {
      setBusy(false);
    }
  }

  async function onEnd() {
    if (!live || busy) return;
    setBusy(true);
    setError(null);
    try {
      const s = await endSession(sessionId);
      setSession(s);
      if (voiceActive) await voice.leave();
      const [t, tr] = await Promise.all([
        getSessionTopics(sessionId),
        getSessionTurns(sessionId),
      ]);
      setTopics(t);
      setTurns(tr);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "End failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto min-h-screen max-w-[720px] px-6 pb-24 pt-16 md:px-10">
      <header className="rise-in mb-10 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-brand">
            InterviewBuddy
          </p>
          <h1 className="font-heading text-[32px] font-semibold leading-[1.1] tracking-[-0.022em] text-foreground md:text-[40px]">
            Live grill
          </h1>
          <p className="mt-2 text-[15px] text-foreground/85">
            Answer out loud with voice, or type.
          </p>
        </div>
        <div className="text-right">
          <p className="font-mono text-[28px] font-semibold tabular-nums tracking-tight text-foreground">
            {formatCountdown(remaining)}
          </p>
          <p className="text-[12px] uppercase tracking-[0.12em] text-muted-foreground">
            {completed ? "at wrap" : "remaining"}
          </p>
        </div>
      </header>

      {error && (
        <Alert className="mb-6 border-destructive/30">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="mb-6 flex flex-wrap items-center gap-3">
        {session && (
          <Badge
            className={
              completed
                ? "border-transparent bg-secondary font-mono text-link"
                : "border-transparent bg-brand-soft font-mono text-brand"
            }
          >
            {session.status}
          </Badge>
        )}
        {activeTopic && (
          <span className="text-[15px] text-foreground">
            Topic: <span className="font-medium">{activeTopic.title}</span>
            <span className="ml-2 font-mono text-[12px] text-muted-foreground">
              {activeTopic.kind}
            </span>
          </span>
        )}
      </div>

      {live && voiceEnabled && (
        <Card className="mb-6 shadow-none ring-border">
          <CardHeader>
            <CardTitle className="flex items-center gap-3 text-[17px] font-semibold tracking-[-0.01em]">
              Voice
              <Badge
                className={
                  voiceTalking
                    ? "border-transparent bg-brand-soft font-mono text-brand"
                    : "border-transparent bg-secondary font-mono text-muted-foreground"
                }
              >
                {voicePhaseLabel(voice.phase)}
              </Badge>
            </CardTitle>
            <CardDescription>
              The interviewer asks each question out loud. Answer at your own pace, then
              press Submit answer. Leaving the call ends the interview.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {voice.error && (
              <Alert className="border-destructive/30">
                <AlertDescription>{voice.error}</AlertDescription>
              </Alert>
            )}
            {voiceTalking && (
              <p
                className={
                  voice.agentLate
                    ? "text-[14px] font-medium text-destructive"
                    : "text-[14px] text-muted-foreground"
                }
              >
                {interviewerStatus({
                  joined: voice.agentJoined,
                  state: voice.agentState,
                  waitedTooLong: voice.agentLate,
                  awaitingReply: voice.awaitingReply,
                })}
              </p>
            )}
            {voiceTalking && voice.notice && (
              <p className="text-[14px] font-medium text-destructive">{voice.notice}</p>
            )}
            {voiceTalking && (
              <div
                className="rounded-lg border border-border bg-muted/40 px-4 py-3"
                aria-live="polite"
              >
                <div className="mb-2 flex items-center gap-2">
                  <span
                    className={
                      voice.userSpeaking && !voice.muted
                        ? "size-2 rounded-full bg-brand"
                        : "size-2 rounded-full bg-muted-foreground/40"
                    }
                    aria-hidden
                  />
                  <span className="font-mono text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {voice.muted
                      ? "Mic muted"
                      : voice.userSpeaking
                        ? "Hearing you"
                        : "What the interviewer hears"}
                  </span>
                </div>
                {voice.heard.length === 0 ? (
                  <p className="text-[15px] text-muted-foreground">
                    {!voice.agentJoined
                      ? "Live transcription starts once the interviewer joins."
                      : voice.agentState === "speaking"
                        ? "Listen to the question, then answer when it finishes."
                        : "Take your time. Pauses are fine — nothing is sent until you press Submit answer."}
                  </p>
                ) : (
                  <div className="space-y-1">
                    {voice.heard.map((seg) => (
                      <p
                        key={seg.id}
                        className={
                          seg.final
                            ? "text-[15px] leading-relaxed text-foreground"
                            : "text-[15px] leading-relaxed text-foreground/60 italic"
                        }
                      >
                        {seg.text}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}
            {voiceTalking && voice.agentJoined && (
              <div className="flex flex-wrap gap-3">
                <Button
                  type="button"
                  onClick={() => void voice.submitAnswer()}
                  disabled={
                    !canSubmitVoiceAnswer({
                      joined: voice.agentJoined,
                      state: voice.agentState,
                      awaitingReply: voice.awaitingReply,
                      submitting: voice.submitting,
                      heard: voice.heard,
                    })
                  }
                  className="rounded-lg bg-brand font-semibold text-white hover:bg-brand/90"
                >
                  {voice.submitting ? "Submitting…" : "Submit answer"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void voice.clearAnswer()}
                  disabled={
                    voice.submitting || voice.awaitingReply || voice.heard.length === 0
                  }
                  className="rounded-full"
                >
                  Clear and restart answer
                </Button>
              </div>
            )}
            <div className="flex flex-wrap gap-3">
              {canJoinVoice({
                sessionStatus: session?.status,
                voiceEnabled,
                phase: voice.phase,
              }) && (
                <Button
                  type="button"
                  onClick={() => void voice.join()}
                  className="rounded-lg bg-brand font-semibold text-white hover:bg-brand/90"
                >
                  Join voice
                </Button>
              )}
              {voiceTalking && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void voice.toggleMute()}
                  className="rounded-full"
                  aria-pressed={voice.muted}
                >
                  {voice.muted ? "Unmute mic" : "Mute mic"}
                </Button>
              )}
              {voiceTalking && voice.audioBlocked && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void voice.unlockAudio()}
                  className="rounded-full"
                >
                  Enable audio
                </Button>
              )}
            </div>
            <div ref={voice.audioHostRef} className="hidden" aria-hidden />
          </CardContent>
        </Card>
      )}

      <Card className="mb-6 shadow-none ring-border">
        <CardHeader>
          <CardTitle className="text-[17px] font-semibold tracking-[-0.01em]">
            Transcript
          </CardTitle>
          <CardDescription>
            Timed text grill grounded in your prepared resume.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-0">
          {turns.length === 0 && (
            <p className="text-[15px] text-muted-foreground">Loading turns…</p>
          )}
          {turns.map((turn) => (
            <div key={turn.id}>
              <div className="flex gap-4 py-4">
                <span
                  className={
                    turn.role === "agent"
                      ? "w-16 shrink-0 font-mono text-[12px] font-semibold uppercase tracking-wide text-brand"
                      : "w-16 shrink-0 font-mono text-[12px] font-semibold uppercase tracking-wide text-link"
                  }
                >
                  {turn.role === "agent" ? "Agent" : "You"}
                </span>
                <p className="text-[15px] leading-relaxed text-foreground">
                  {displayTurnText(turn)}
                </p>
              </div>
              <Separator />
            </div>
          ))}
        </CardContent>
      </Card>

      {live && voiceActive && (
        <Button
          type="button"
          variant="outline"
          onClick={onEnd}
          disabled={busy}
          className="rounded-full"
        >
          End interview
        </Button>
      )}

      {live && !voiceActive && (
        <form onSubmit={onSubmit} className="space-y-4">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type your answer…"
            rows={4}
            disabled={busy}
            className="text-[15px]"
          />
          <div className="flex flex-wrap gap-3">
            <Button
              type="submit"
              disabled={busy || !draft.trim()}
              className="rounded-lg bg-brand font-semibold text-white hover:bg-brand/90"
            >
              {busy ? "Sending…" : "Send answer"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={onEnd}
              disabled={busy}
              className="rounded-full"
            >
              End interview
            </Button>
          </div>
        </form>
      )}

      {completed && (
        <div className="space-y-6">
          <SessionResults sessionId={sessionId} />
          <Link
            href="/"
            className="inline-flex h-8 items-center rounded-full border border-border px-4 text-sm font-medium text-foreground hover:bg-muted"
          >
            Back to prep
          </Link>
        </div>
      )}
    </div>
  );
}
