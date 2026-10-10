const API_BASE =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export const DEV_USER_ID = "00000000-0000-0000-0000-000000000001";

export type HealthResponse = { status: string };

export type Difficulty = "easy" | "medium" | "hard";
export type Seniority = "intern" | "junior" | "mid" | "senior" | "staff";
export type SessionStatus =
  | "preparing"
  | "ready"
  | "live"
  | "completed"
  | "failed";
export type DocType = "resume" | "jd";
export type ParseStatus = "pending" | "processing" | "ready" | "failed";

export type SessionSettings = {
  duration_minutes: number;
  difficulty: Difficulty;
  seniority: Seniority;
};

export type SessionOut = {
  id: string;
  user_id: string;
  status: SessionStatus;
  settings: Record<string, unknown>;
  resume_document_id: string | null;
  jd_document_id: string | null;
  n_target: number | null;
  lexicon: Record<string, unknown>;
  started_at: string | null;
  ends_at: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentOut = {
  id: string;
  user_id: string;
  doc_type: DocType;
  content_type: string | null;
  original_filename: string | null;
  byte_size: number | null;
  parse_status: ParseStatus;
  parse_error: string | null;
  raw_text: string | null;
  r2_bucket: string | null;
  r2_key: string | null;
  created_at: string;
  updated_at: string;
};

export type TopicOut = {
  id: string;
  title: string;
  kind: string;
  priority: number;
  status: string;
  claim_id: string | null;
  soft_cap_seconds: number;
  hard_cap_seconds: number;
  rollup_scores?: TopicRollup | Record<string, never>;
};

export const RUBRIC_DIMS = [
  "correctness",
  "relevance",
  "depth",
  "structure",
  "honesty",
] as const;
export type RubricDim = (typeof RUBRIC_DIMS)[number];
export type HireSignal = "needs_work" | "mixed" | "solid" | "strong";
export type Coverage = "grilled" | "light" | "skipped";

export type TopicRollup = {
  n_turns: number;
  coverage: Coverage;
  composite: number | null;
  dims: Partial<Record<RubricDim, number>>;
  flags: Partial<Record<"bluff" | "contradiction" | "idk", number>>;
};

export type ResultItem = {
  topic_id: string;
  title: string;
  kind: string;
  score: number | null;
  reason: string;
  severity?: "major" | "minor";
};

export type TurnScoreOut = Record<RubricDim, number> & {
  turn_id: string;
  topic_id: string | null;
  answer: string;
  confidence: number | null;
  rationale: string | null;
  flags: Record<string, unknown>;
  evidence: { chunk_id: string; quote: string; source: string | null }[];
};

export type SessionResultOut = {
  session_id: string;
  overall_score: number | null;
  hire_signal: HireSignal | null;
  strengths: ResultItem[];
  gaps: ResultItem[];
  coverage_summary: {
    counts?: Record<Coverage, number>;
    jd_must?: Record<Coverage, number>;
    dims?: Partial<Record<RubricDim, number>>;
    topics?: { topic_id: string; title: string; kind: string; coverage: Coverage }[];
  };
  topics: TopicOut[];
  turn_scores: TurnScoreOut[];
};

export type TranscriptCorrection = {
  from: string;
  to: string;
  method: "exact" | "alias" | "fuzzy" | string;
  score: number;
  start: number;
  end: number;
};

export type TurnOut = {
  id: string;
  role: "agent" | "user" | string;
  raw_text: string;
  normalized_text?: string | null;
  corrections?: TranscriptCorrection[];
  topic_id: string | null;
  frontier_node_id: string | null;
  created_at: string;
};

export type AnswerOut = {
  session: SessionOut;
  user_turn: TurnOut;
  agent_turn: TurnOut | null;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail != null) return JSON.stringify(body.detail);
  } catch {
    /* ignore */
  }
  return `Request failed: ${res.status}`;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(res.status, await readError(res));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function getHealth(): Promise<HealthResponse> {
  return api<HealthResponse>("/health");
}

export async function ensureDevUser(): Promise<void> {
  const res = await fetch(`${API_BASE}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: DEV_USER_ID,
      email: "dev@interviewbuddy.local",
      name: "Dev",
    }),
    cache: "no-store",
  });
  if (res.ok || res.status === 409) return;
  throw new ApiError(res.status, await readError(res));
}

export async function createSession(
  settings: SessionSettings,
): Promise<SessionOut> {
  return api<SessionOut>("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings }),
  });
}

export async function getSession(sessionId: string): Promise<SessionOut> {
  return api<SessionOut>(`/sessions/${sessionId}`);
}

export async function startSession(sessionId: string): Promise<SessionOut> {
  return api<SessionOut>(`/sessions/${sessionId}/start`, { method: "POST" });
}

export async function getSessionTopics(sessionId: string): Promise<TopicOut[]> {
  return api<TopicOut[]>(`/sessions/${sessionId}/topics`);
}

export async function getSessionTurns(sessionId: string): Promise<TurnOut[]> {
  return api<TurnOut[]>(`/sessions/${sessionId}/turns`);
}

export async function answerSession(
  sessionId: string,
  text: string,
): Promise<AnswerOut> {
  return api<AnswerOut>(`/sessions/${sessionId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function endSession(sessionId: string): Promise<SessionOut> {
  return api<SessionOut>(`/sessions/${sessionId}/end`, { method: "POST" });
}

export async function getSessionResults(
  sessionId: string,
): Promise<SessionResultOut> {
  return api<SessionResultOut>(`/sessions/${sessionId}/results`);
}

export type ReportStatus = "pending" | "ready" | "failed";

export type SessionReportOut = {
  session_id: string;
  status: ReportStatus;
  report_json: Record<string, unknown> | null;
  report_markdown: string | null;
  r2_pdf_key: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export async function getSessionReport(
  sessionId: string,
): Promise<SessionReportOut> {
  return api<SessionReportOut>(`/sessions/${sessionId}/report`);
}

export async function retrySessionReport(
  sessionId: string,
): Promise<SessionReportOut> {
  return api<SessionReportOut>(`/sessions/${sessionId}/report/retry`, {
    method: "POST",
  });
}

export type TranscriptExportOut = {
  path: string;
  filename: string;
  session_id: string;
};

export async function exportSessionTranscript(
  sessionId: string,
): Promise<TranscriptExportOut> {
  return api<TranscriptExportOut>(`/sessions/${sessionId}/export`, { method: "POST" });
}

export type VoiceStatusOut = { enabled: boolean };

export type VoiceTokenOut = {
  server_url: string;
  room_name: string;
  participant_identity: string;
  token: string;
  expires_at: string;
};

export async function getVoiceStatus(): Promise<VoiceStatusOut> {
  return api<VoiceStatusOut>("/voice/status");
}

export async function getVoiceToken(sessionId: string): Promise<VoiceTokenOut> {
  return api<VoiceTokenOut>(`/sessions/${sessionId}/voice/token`, {
    method: "POST",
  });
}

export async function getDocument(documentId: string): Promise<DocumentOut> {
  return api<DocumentOut>(`/documents/${documentId}`);
}

export async function uploadDocument(
  sessionId: string,
  docType: DocType,
  file: File,
): Promise<DocumentOut> {
  const form = new FormData();
  form.append("doc_type", docType);
  form.append("file", file);
  return api<DocumentOut>(`/sessions/${sessionId}/documents`, {
    method: "POST",
    body: form,
  });
}

export async function pasteDocument(
  sessionId: string,
  docType: DocType,
  text: string,
): Promise<DocumentOut> {
  return api<DocumentOut>(`/sessions/${sessionId}/documents/paste`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_type: docType, text }),
  });
}

export { API_BASE };
