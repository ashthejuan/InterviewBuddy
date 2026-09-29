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
  type SessionOut,
  type TopicOut,
  type TurnOut,
} from "@/lib/api";
import { formatCountdown, secondsRemaining } from "@/lib/timer";
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

export function LiveInterview({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<SessionOut | null>(null);
  const [topics, setTopics] = useState<TopicOut[]>([]);
  const [turns, setTurns] = useState<TurnOut[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

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
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const remaining = secondsRemaining(session?.ends_at ?? null, nowMs);
  const activeTopic = topics.find((t) => t.status === "active") ?? null;
  const completed = session?.status === "completed";
  const live = session?.status === "live";

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
      const t = await getSessionTopics(sessionId);
      setTopics(t);
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
            Text path — voice arrives later.
          </p>
        </div>
        <div className="text-right">
          <p className="font-mono text-[28px] font-semibold tabular-nums tracking-tight text-foreground">
            {formatCountdown(remaining)}
          </p>
          <p className="text-[12px] uppercase tracking-[0.12em] text-muted-foreground">
            remaining
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
                  {turn.raw_text}
                </p>
              </div>
              <Separator />
            </div>
          ))}
        </CardContent>
      </Card>

      {live && (
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
        <Card className="shadow-none ring-border">
          <CardHeader>
            <CardTitle className="text-[17px] font-semibold">Session complete</CardTitle>
            <CardDescription>
              Scoring and debrief come in later phases. You can start another prep
              from home.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              href="/"
              className="inline-flex h-8 items-center rounded-full border border-border px-4 text-sm font-medium text-foreground hover:bg-muted"
            >
              Back to prep
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
