"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  createSession,
  ensureDevUser,
  getDocument,
  getSession,
  getSessionTopics,
  pasteDocument,
  startSession,
  uploadDocument,
  type Difficulty,
  type DocumentOut,
  type Seniority,
  type SessionOut,
  type TopicOut,
} from "@/lib/api";
import {
  canStartInterview,
  isPrepInFlight,
  prepareActionLabel,
  prepLabel,
  showPrepareAction,
} from "@/lib/prep";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { LogoutButton } from "@/components/LogoutButton";

type InputMode = "file" | "paste";

const DURATIONS = [15, 20, 30, 45, 60] as const;
const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];
const SENIORITIES: Seniority[] = ["intern", "junior", "mid", "senior", "staff"];
const ACCEPT = ".pdf,.txt,.docx,.md,.markdown,text/plain,application/pdf";

function DocPanel({
  label,
  required,
  mode,
  onMode,
  fileName,
  onFile,
  paste,
  onPaste,
  doc,
  disabled,
}: {
  label: string;
  required?: boolean;
  mode: InputMode;
  onMode: (m: InputMode) => void;
  fileName: string | null;
  onFile: (f: File | null) => void;
  paste: string;
  onPaste: (t: string) => void;
  doc: DocumentOut | null;
  disabled?: boolean;
}) {
  return (
    <Card className="shadow-none ring-border">
      <CardHeader className="flex-row items-baseline justify-between gap-3 space-y-0">
        <CardTitle className="text-[17px] font-semibold tracking-[-0.01em]">
          {label}
          {required ? (
            <span className="ml-1 text-brand">*</span>
          ) : (
            <span className="ml-2 text-[13px] font-normal text-muted-foreground">
              optional
            </span>
          )}
        </CardTitle>
        {doc && (
          <Badge
            variant="outline"
            className={
              doc.parse_status === "failed"
                ? "border-transparent bg-brand-soft font-mono text-brand"
                : doc.parse_status === "ready"
                  ? "border-transparent bg-secondary font-mono text-link"
                  : "font-mono text-muted-foreground"
            }
          >
            {doc.parse_status}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant={mode === "file" ? "default" : "secondary"}
            disabled={disabled}
            onClick={() => onMode("file")}
          >
            Upload file
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === "paste" ? "default" : "secondary"}
            disabled={disabled}
            onClick={() => onMode("paste")}
          >
            Paste text
          </Button>
        </div>

        {mode === "file" ? (
          <label className="flex cursor-pointer flex-col items-start gap-2 rounded-[10px] border border-dashed border-input bg-muted/40 px-4 py-5 transition hover:border-muted-foreground/40">
            <span className="text-sm font-medium text-foreground">
              {fileName ?? "Choose PDF, DOCX, TXT, or Markdown"}
            </span>
            <span className="text-[13px] text-muted-foreground">Max 5 MB</span>
            <input
              type="file"
              accept={ACCEPT}
              disabled={disabled}
              className="sr-only"
              onChange={(e) => onFile(e.target.files?.[0] ?? null)}
            />
          </label>
        ) : (
          <Textarea
            value={paste}
            disabled={disabled}
            onChange={(e) => onPaste(e.target.value)}
            placeholder="Paste resume or job description…"
            rows={7}
            className="min-h-40 resize-y bg-muted/40"
          />
        )}

        {doc?.parse_error && (
          <p className="text-sm text-brand">{doc.parse_error}</p>
        )}
      </CardContent>
    </Card>
  );
}

export function PrepareInterview() {
  const router = useRouter();
  const [duration, setDuration] = useState(30);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [seniority, setSeniority] = useState<Seniority>("mid");

  const [resumeMode, setResumeMode] = useState<InputMode>("file");
  const [jdMode, setJdMode] = useState<InputMode>("file");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [resumePaste, setResumePaste] = useState("");
  const [jdPaste, setJdPaste] = useState("");

  const [session, setSession] = useState<SessionOut | null>(null);
  const [resumeDoc, setResumeDoc] = useState<DocumentOut | null>(null);
  const [jdDoc, setJdDoc] = useState<DocumentOut | null>(null);
  const [topics, setTopics] = useState<TopicOut[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  const polling = useRef(false);

  const refreshPrep = useCallback(async (sessionId: string) => {
    const s = await getSession(sessionId);
    setSession(s);

    if (s.resume_document_id) {
      const d = await getDocument(s.resume_document_id);
      setResumeDoc(d);
    }
    if (s.jd_document_id) {
      const d = await getDocument(s.jd_document_id);
      setJdDoc(d);
    }

    if (s.status === "ready") {
      const t = await getSessionTopics(sessionId);
      setTopics(t);
    }

    return s;
  }, []);

  useEffect(() => {
    if (!session || started) return;
    if (session.status !== "preparing") return;

    polling.current = true;
    const id = window.setInterval(async () => {
      if (!polling.current) return;
      try {
        const s = await refreshPrep(session.id);
        if (s.status !== "preparing") {
          polling.current = false;
          window.clearInterval(id);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Polling failed");
      }
    }, 1500);

    return () => {
      polling.current = false;
      window.clearInterval(id);
    };
  }, [session, started, refreshPrep]);

  async function onPrepare(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const hasResume =
      resumeMode === "file" ? !!resumeFile : resumePaste.trim().length > 0;
    if (!hasResume) {
      setError("Resume is required — upload a file or paste text.");
      return;
    }

    setBusy(true);
    try {
      await ensureDevUser();
      const created = await createSession({
        duration_minutes: duration,
        difficulty,
        seniority,
      });
      setSession(created);
      setResumeDoc(null);
      setJdDoc(null);
      setTopics([]);
      setStarted(false);

      const resume =
        resumeMode === "file"
          ? await uploadDocument(created.id, "resume", resumeFile!)
          : await pasteDocument(created.id, "resume", resumePaste.trim());
      setResumeDoc(resume);

      const hasJd = jdMode === "file" ? !!jdFile : jdPaste.trim().length > 0;
      if (hasJd) {
        const jd =
          jdMode === "file"
            ? await uploadDocument(created.id, "jd", jdFile!)
            : await pasteDocument(created.id, "jd", jdPaste.trim());
        setJdDoc(jd);
      }

      await refreshPrep(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Prepare failed");
    } finally {
      setBusy(false);
    }
  }

  async function onStart() {
    if (!session || !canStartInterview(session.status)) return;
    setBusy(true);
    setError(null);
    try {
      const live = await startSession(session.id);
      setSession(live);
      setStarted(true);
      router.push(`/sessions/${live.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Start failed");
    } finally {
      setBusy(false);
    }
  }

  const status = session?.status ?? null;
  const prepInFlight = isPrepInFlight(status, busy);
  const ready = status ? canStartInterview(status) : false;
  const showPrepare = showPrepareAction(status);
  const lexiconSkills = Array.isArray(session?.lexicon?.skills)
    ? (session!.lexicon.skills as string[])
    : [];

  return (
    <div className="mx-auto min-h-screen max-w-[980px] px-6 pb-24 pt-16 md:px-10">
      <div className="rise-in mb-8 flex items-center justify-between gap-4">
        <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-brand">
          InterviewBuddy
        </p>
        <LogoutButton />
      </div>
      <header className="rise-in mb-14 max-w-[620px]">
        <h1 className="mb-4 font-heading text-[40px] font-semibold leading-[1.08] tracking-[-0.022em] text-foreground md:text-[48px]">
          Prep before you grill.
        </h1>
        <p className="max-w-[60ch] text-[17px] text-foreground/85">
          Upload a resume and optional job description. We parse, chunk, and
          plan topics — then unlock Start when the session is ready.
        </p>
      </header>

      <form onSubmit={onPrepare} className="rise-in space-y-6">
        <Card className="shadow-none ring-border">
          <CardHeader>
            <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-brand">
              Session settings
            </p>
            <CardDescription>
              Duration, difficulty, and seniority feed topic planning.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-5 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label className="text-[13px] font-normal text-muted-foreground">
                  Duration
                </Label>
                <Select
                  value={String(duration)}
                  onValueChange={(v) => {
                    if (v != null) setDuration(Number(v));
                  }}
                  disabled={prepInFlight}
                >
                  <SelectTrigger className="w-full bg-muted/40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DURATIONS.map((d) => (
                      <SelectItem key={d} value={String(d)}>
                        {d} min
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-[13px] font-normal text-muted-foreground">
                  Difficulty
                </Label>
                <Select
                  value={difficulty}
                  onValueChange={(v) => {
                    if (v != null) setDifficulty(v as Difficulty);
                  }}
                  disabled={prepInFlight}
                >
                  <SelectTrigger className="w-full bg-muted/40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DIFFICULTIES.map((d) => (
                      <SelectItem key={d} value={d}>
                        {d}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-[13px] font-normal text-muted-foreground">
                  Seniority
                </Label>
                <Select
                  value={seniority}
                  onValueChange={(v) => {
                    if (v != null) setSeniority(v as Seniority);
                  }}
                  disabled={prepInFlight}
                >
                  <SelectTrigger className="w-full bg-muted/40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SENIORITIES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        <DocPanel
          label="Resume"
          required
          mode={resumeMode}
          onMode={setResumeMode}
          fileName={resumeFile?.name ?? null}
          onFile={setResumeFile}
          paste={resumePaste}
          onPaste={setResumePaste}
          doc={resumeDoc}
          disabled={prepInFlight}
        />

        <DocPanel
          label="Job description"
          mode={jdMode}
          onMode={setJdMode}
          fileName={jdFile?.name ?? null}
          onFile={setJdFile}
          paste={jdPaste}
          onPaste={setJdPaste}
          doc={jdDoc}
          disabled={prepInFlight}
        />

        <div className="flex flex-wrap items-center gap-3 pt-2">
          {showPrepare && (
            <Button
              type="submit"
              disabled={prepInFlight}
              size="lg"
              className="h-11 rounded-[980px] px-6 text-[15px]"
            >
              {prepareActionLabel(status)}
            </Button>
          )}
          <Button
            type="button"
            onClick={onStart}
            disabled={!ready || prepInFlight}
            size="lg"
            className="h-11 rounded-lg bg-brand px-6 text-[15px] font-semibold text-white hover:bg-brand/90 disabled:opacity-50"
          >
            Start interview
          </Button>
          {prepInFlight && (
            <span
              role="status"
              aria-label="Preparing documents"
              className="inline-flex h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-brand"
            />
          )}
        </div>
      </form>

      {error && (
        <Alert
          variant="destructive"
          className="mt-6 border-border bg-secondary"
        >
          <AlertDescription className="text-brand">{error}</AlertDescription>
        </Alert>
      )}

      {session && (
        <Card className="rise-in mt-10 shadow-none ring-border">
          <CardHeader>
            <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-brand">
              Prep status
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <CardTitle className="text-[22px] font-semibold tracking-[-0.01em]">
                {prepLabel(session.status)}
              </CardTitle>
              {session.status === "preparing" && (
                <span
                  role="status"
                  aria-label="Preparing documents"
                  className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-brand"
                />
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            {started && session.status === "live" && (
              <p className="text-[15px] text-foreground/85">
                Opening live grill…
              </p>
            )}

            {lexiconSkills.length > 0 && (
              <div>
                <p className="mb-2 text-[13px] text-muted-foreground">
                  Lexicon skills
                </p>
                <div className="flex flex-wrap gap-2">
                  {lexiconSkills.slice(0, 12).map((s) => (
                    <Badge
                      key={s}
                      className="border-transparent bg-brand-soft font-mono text-brand"
                    >
                      {s}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {topics.length > 0 && (
              <div>
                <p className="mb-3 text-[13px] text-muted-foreground">
                  Planned topics
                </p>
                <Separator />
                <ul>
                  {topics.map((t) => (
                    <li key={t.id}>
                      <div className="py-3 text-[15px] text-foreground">
                        {t.title}
                      </div>
                      <Separator />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* <p className="mt-16 max-w-[42ch] font-serif text-[22px] italic leading-snug text-foreground/85">
        “Every question points back to your resume.”
      </p> */}
    </div>
  );
}
