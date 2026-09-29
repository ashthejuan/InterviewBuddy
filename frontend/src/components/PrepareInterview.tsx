"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
import { canStartInterview, prepLabel } from "@/lib/prep";

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
    <section className="rounded-[14px] border border-hairline bg-white p-6">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h3 className="text-[17px] font-semibold tracking-[-0.01em] text-ink">
          {label}
          {required ? (
            <span className="ml-1 text-accent">*</span>
          ) : (
            <span className="ml-2 text-[13px] font-normal text-muted">
              optional
            </span>
          )}
        </h3>
        {doc && (
          <span
            className={`font-mono text-[12px] ${
              doc.parse_status === "failed"
                ? "text-accent"
                : doc.parse_status === "ready"
                  ? "text-accent-ink"
                  : "text-muted"
            }`}
          >
            {doc.parse_status}
          </span>
        )}
      </div>

      <div className="mb-4 flex gap-2 text-[14px]">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onMode("file")}
          className={`rounded-lg px-3 py-1.5 ${
            mode === "file"
              ? "bg-ink text-white"
              : "bg-paper text-ink-soft hover:bg-cream"
          }`}
        >
          Upload file
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onMode("paste")}
          className={`rounded-lg px-3 py-1.5 ${
            mode === "paste"
              ? "bg-ink text-white"
              : "bg-paper text-ink-soft hover:bg-cream"
          }`}
        >
          Paste text
        </button>
      </div>

      {mode === "file" ? (
        <label className="flex cursor-pointer flex-col items-start gap-2 rounded-[10px] border border-dashed border-hairline bg-paper px-4 py-5 transition hover:border-muted">
          <span className="text-[14px] font-medium text-ink">
            {fileName ?? "Choose PDF, DOCX, TXT, or Markdown"}
          </span>
          <span className="text-[13px] text-muted">Max 5 MB</span>
          <input
            type="file"
            accept={ACCEPT}
            disabled={disabled}
            className="sr-only"
            onChange={(e) => onFile(e.target.files?.[0] ?? null)}
          />
        </label>
      ) : (
        <textarea
          value={paste}
          disabled={disabled}
          onChange={(e) => onPaste(e.target.value)}
          placeholder="Paste resume or job description…"
          rows={7}
          className="w-full resize-y rounded-[10px] border border-hairline bg-paper px-3 py-2.5 text-[15px] text-ink-soft outline-none focus:border-ink"
        />
      )}

      {doc?.parse_error && (
        <p className="mt-3 text-[14px] text-accent">{doc.parse_error}</p>
      )}
    </section>
  );
}

export function PrepareInterview() {
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

      const hasJd =
        jdMode === "file" ? !!jdFile : jdPaste.trim().length > 0;
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
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Start failed");
    } finally {
      setBusy(false);
    }
  }

  const ready = session ? canStartInterview(session.status) : false;
  const lexiconSkills = Array.isArray(session?.lexicon?.skills)
    ? (session!.lexicon.skills as string[])
    : [];

  return (
    <div className="mx-auto min-h-screen max-w-[980px] px-6 pb-24 pt-16 md:px-10">
      <header className="rise-in mb-14 max-w-[620px]">
        <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-accent">
          InterviewBuddy
        </p>
        <h1 className="mb-4 text-[40px] font-semibold leading-[1.08] tracking-[-0.022em] text-ink md:text-[48px]">
          Prep before you grill.
        </h1>
        <p className="text-[17px] text-ink-soft">
          Upload a resume and optional job description. We parse, chunk, and
          plan topics — then unlock Start when the session is ready.
        </p>
      </header>

      <form onSubmit={onPrepare} className="rise-in space-y-6">
        <section className="rounded-[14px] border border-hairline bg-white p-6">
          <p className="mb-4 text-[12px] font-semibold uppercase tracking-[0.14em] text-accent">
            Session settings
          </p>
          <div className="grid gap-5 sm:grid-cols-3">
            <label className="block text-[13px] text-muted">
              Duration
              <select
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                disabled={busy}
                className="mt-1.5 w-full rounded-lg border border-hairline bg-paper px-3 py-2.5 text-[15px] text-ink outline-none focus:border-ink"
              >
                {DURATIONS.map((d) => (
                  <option key={d} value={d}>
                    {d} min
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-[13px] text-muted">
              Difficulty
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value as Difficulty)}
                disabled={busy}
                className="mt-1.5 w-full rounded-lg border border-hairline bg-paper px-3 py-2.5 text-[15px] text-ink outline-none focus:border-ink"
              >
                {DIFFICULTIES.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-[13px] text-muted">
              Seniority
              <select
                value={seniority}
                onChange={(e) => setSeniority(e.target.value as Seniority)}
                disabled={busy}
                className="mt-1.5 w-full rounded-lg border border-hairline bg-paper px-3 py-2.5 text-[15px] text-ink outline-none focus:border-ink"
              >
                {SENIORITIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

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
          disabled={busy}
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
          disabled={busy}
        />

        <div className="flex flex-wrap items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-ink px-6 py-3 text-[16px] font-medium text-white disabled:opacity-50"
          >
            {busy ? "Working…" : session ? "Re-prepare" : "Prepare session"}
          </button>
          <button
            type="button"
            onClick={onStart}
            disabled={!ready || busy}
            className="rounded-lg bg-accent px-6 py-3 text-[16px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            Start interview
          </button>
        </div>
      </form>

      {error && (
        <p className="mt-6 rounded-[10px] border border-hairline bg-cream px-4 py-3 text-[14px] text-accent">
          {error}
        </p>
      )}

      {session && (
        <section className="rise-in mt-10 rounded-[14px] border border-hairline bg-white p-6">
          <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-accent">
            Prep status
          </p>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <p className="text-[22px] font-semibold tracking-[-0.01em] text-ink">
              {prepLabel(session.status)}
            </p>
            <p className="font-mono text-[13px] text-muted">
              {session.id.slice(0, 8)}…
            </p>
            {session.n_target != null && (
              <p className="text-[14px] text-ink-soft">
                N<sub>target</sub>{" "}
                <span className="font-semibold text-ink">{session.n_target}</span>
              </p>
            )}
          </div>

          {started && session.status === "live" && (
            <p className="mt-4 text-[15px] text-ink-soft">
              Session is live. Text grill UI arrives in Phase 3.
            </p>
          )}

          {lexiconSkills.length > 0 && (
            <div className="mt-5">
              <p className="mb-2 text-[13px] text-muted">Lexicon skills</p>
              <div className="flex flex-wrap gap-2">
                {lexiconSkills.slice(0, 12).map((s) => (
                  <span
                    key={s}
                    className="rounded-full bg-[rgba(255,102,0,0.1)] px-3 py-1 text-[12px] font-semibold text-accent"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {topics.length > 0 && (
            <div className="mt-6">
              <p className="mb-3 text-[13px] text-muted">Planned topics</p>
              <ul className="divide-y divide-hairline border-t border-hairline">
                {topics.map((t) => (
                  <li
                    key={t.id}
                    className="flex items-baseline justify-between gap-4 py-3 text-[15px]"
                  >
                    <span className="text-ink">{t.title}</span>
                    <span className="shrink-0 font-mono text-[12px] text-muted">
                      {t.kind}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <p className="mt-16 max-w-[42ch] font-serif text-[22px] italic leading-snug text-ink-soft">
        “Every question points back to your resume.”
      </p>
    </div>
  );
}
