"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  RUBRIC_DIMS,
  exportSessionTranscript,
  getSessionReport,
  getSessionResults,
  retrySessionReport,
  type HireSignal,
  type ResultItem,
  type SessionReportOut,
  type SessionResultOut,
  type TopicRollup,
} from "@/lib/api";
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

const SIGNAL_LABEL: Record<HireSignal, string> = {
  needs_work: "Needs work",
  mixed: "Mixed",
  solid: "Solid",
  strong: "Strong",
};

const REPORT_POLL_MS = 1500;

type ReportProse = {
  summary?: string | null;
  pros?: string[];
  cons?: string[];
  next_steps?: string[];
};

function fmt(score: number | null | undefined): string {
  return score == null ? "—" : score.toFixed(1);
}

function DimBar({ label, value }: { label: string; value: number | undefined }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, (value / 5) * 100));
  return (
    <div className="flex items-center gap-3">
      <span className="w-24 shrink-0 text-[13px] capitalize text-muted-foreground">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full bg-brand" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right font-mono text-[12px] tabular-nums text-foreground">
        {fmt(value)}
      </span>
    </div>
  );
}

function ItemList({ title, items }: { title: string; items: ResultItem[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {title}
      </p>
      <ul className="space-y-1.5">
        {items.map((it) => (
          <li key={`${title}-${it.topic_id}`} className="text-[15px] text-foreground">
            {it.severity === "major" && (
              <Badge variant="destructive" className="mr-2 align-middle">
                Major
              </Badge>
            )}
            <span className="font-medium">{it.title}</span>
            <span className="text-muted-foreground"> — {it.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function downloadMarkdown(sessionId: string, markdown: string) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `interview-report-${sessionId.slice(0, 8)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

function proseFromReport(report: SessionReportOut | null): ReportProse | null {
  const json = report?.report_json;
  if (!json || typeof json !== "object") return null;
  const prose = (json as { prose?: ReportProse }).prose;
  return prose ?? null;
}

export function SessionResults({ sessionId }: { sessionId: string }) {
  const [result, setResult] = useState<SessionResultOut | null>(null);
  const [report, setReport] = useState<SessionReportOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reportErr, setReportErr] = useState<string | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [exportErr, setExportErr] = useState<string | null>(null);
  const [retryBusy, setRetryBusy] = useState(false);
  const [pollToken, setPollToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getSessionResults(sessionId)
      .then((r) => !cancelled && setResult(r))
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load results");
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const r = await getSessionReport(sessionId);
        if (cancelled) return;
        setReport(r);
        setReportErr(null);
        if (r.status === "pending") {
          timer = setTimeout(poll, REPORT_POLL_MS);
        }
      } catch (err) {
        if (!cancelled) {
          setReportErr(err instanceof ApiError ? err.message : "Failed to load report");
        }
      }
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [sessionId, pollToken]);

  async function onExport() {
    if (exportBusy) return;
    setExportBusy(true);
    setExportErr(null);
    setExportMsg(null);
    try {
      const out = await exportSessionTranscript(sessionId);
      setExportMsg(`Saved ${out.filename} to interview_logs/`);
    } catch (err) {
      setExportErr(err instanceof ApiError ? err.message : "Export failed");
    } finally {
      setExportBusy(false);
    }
  }

  async function onRetryReport() {
    if (retryBusy) return;
    setRetryBusy(true);
    setReportErr(null);
    try {
      const r = await retrySessionReport(sessionId);
      setReport(r);
      setPollToken((n) => n + 1);
    } catch (err) {
      setReportErr(err instanceof ApiError ? err.message : "Retry failed");
    } finally {
      setRetryBusy(false);
    }
  }

  if (error) {
    return (
      <Alert className="border-destructive/30">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }
  if (!result) {
    return <p className="text-[15px] text-muted-foreground">Scoring your interview…</p>;
  }

  const dims = result.coverage_summary.dims ?? {};
  const counts = result.coverage_summary.counts;
  const prose = proseFromReport(report);

  return (
    <Card className="shadow-none ring-border">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-3 text-[17px] font-semibold">
          Results
          {result.hire_signal && (
            <Badge className="border-transparent bg-brand-soft font-mono text-brand">
              {SIGNAL_LABEL[result.hire_signal]}
            </Badge>
          )}
          <span className="font-mono text-[15px] font-normal tabular-nums text-muted-foreground">
            {fmt(result.overall_score)} / 5
          </span>
        </CardTitle>
        <CardDescription>
          {prose?.summary
            ? prose.summary
            : result.overall_score == null
              ? "No answers were scored in this session."
              : "Practice signal from rubric scores grounded in your resume evidence. Warmup counts lightly."}
          {counts &&
            ` Topics grilled ${counts.grilled}, light ${counts.light}, skipped ${counts.skipped}.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {result.overall_score != null && (
          <div className="space-y-2">
            {RUBRIC_DIMS.map((d) => (
              <DimBar key={d} label={d} value={dims[d]} />
            ))}
          </div>
        )}

        <ItemList title="Strengths" items={result.strengths} />
        <ItemList title="Gaps" items={result.gaps} />

        {prose && (prose.pros?.length || prose.cons?.length) ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {!!prose.pros?.length && (
              <div>
                <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Pros
                </p>
                <ul className="space-y-1.5">
                  {prose.pros.map((p) => (
                    <li key={p} className="text-[15px] text-foreground">
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {!!prose.cons?.length && (
              <div>
                <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Cons
                </p>
                <ul className="space-y-1.5">
                  {prose.cons.map((c) => (
                    <li key={c} className="text-[15px] text-foreground">
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : null}

        {prose?.next_steps && prose.next_steps.length > 0 && (
          <div>
            <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              Next steps
            </p>
            <ol className="list-decimal space-y-1.5 pl-5">
              {prose.next_steps.map((step) => (
                <li key={step} className="text-[15px] text-foreground">
                  {step}
                </li>
              ))}
            </ol>
          </div>
        )}

        <div>
          <p className="mb-1 text-[12px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            By topic
          </p>
          {result.topics.map((t) => {
            const r = t.rollup_scores as TopicRollup | undefined;
            return (
              <div key={t.id}>
                <div className="flex items-baseline justify-between gap-4 py-3">
                  <span className="text-[15px] text-foreground">
                    {t.title}
                    <span className="ml-2 font-mono text-[12px] text-muted-foreground">
                      {t.kind} · {r?.coverage ?? "skipped"}
                    </span>
                  </span>
                  <span className="font-mono text-[13px] tabular-nums text-foreground">
                    {fmt(r?.composite)}
                  </span>
                </div>
                <Separator />
              </div>
            );
          })}
        </div>

        <div className="space-y-2 border-t border-border pt-4">
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={!report?.report_markdown}
              onClick={() =>
                report?.report_markdown && downloadMarkdown(sessionId, report.report_markdown)
              }
            >
              Download report (.md)
            </Button>
            <Button type="button" variant="outline" disabled={exportBusy} onClick={onExport}>
              {exportBusy ? "Exporting…" : "Export transcript JSON"}
            </Button>
            {report?.status === "failed" && (
              <Button type="button" variant="outline" disabled={retryBusy} onClick={onRetryReport}>
                {retryBusy ? "Retrying…" : "Retry report"}
              </Button>
            )}
          </div>
          {report?.status === "pending" && (
            <p className="font-mono text-[13px] text-muted-foreground">Building structured report…</p>
          )}
          {exportMsg && <p className="font-mono text-[13px] text-link">{exportMsg}</p>}
          {(exportErr || reportErr) && (
            <Alert className="border-destructive/30">
              <AlertDescription>{exportErr || reportErr}</AlertDescription>
            </Alert>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
