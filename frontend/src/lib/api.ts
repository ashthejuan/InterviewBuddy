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
