import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createSession,
  ensureDevUser,
  getDocument,
  getSession,
  pasteDocument,
  startSession,
  uploadDocument,
} from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function stubFetch(handler: (input: RequestInfo | URL, init?: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
      Promise.resolve(handler(input, init)),
    ),
  );
}

describe("ensureDevUser", () => {
  it("creates the fixed dev user when missing", async () => {
    stubFetch((input, init) => {
      expect(String(input)).toMatch(/\/users$/);
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body));
      expect(body.id).toBe("00000000-0000-0000-0000-000000000001");
      return new Response(JSON.stringify({ id: body.id, email: body.email, name: "Dev", created_at: "" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    });
    await ensureDevUser();
  });

  it("treats 409 as already seeded", async () => {
    stubFetch(() => new Response(JSON.stringify({ detail: "email already registered" }), { status: 409 }));
    await expect(ensureDevUser()).resolves.toBeUndefined();
  });
});

describe("createSession", () => {
  it("posts settings and returns the session", async () => {
    stubFetch((input, init) => {
      expect(String(input)).toMatch(/\/sessions$/);
      expect(JSON.parse(String(init?.body))).toEqual({
        settings: { duration_minutes: 20, difficulty: "hard", seniority: "senior" },
      });
      return new Response(
        JSON.stringify({
          id: "11111111-1111-1111-1111-111111111111",
          user_id: "00000000-0000-0000-0000-000000000001",
          status: "preparing",
          settings: { duration_minutes: 20, difficulty: "hard", seniority: "senior" },
          resume_document_id: null,
          jd_document_id: null,
          n_target: null,
          lexicon: {},
          created_at: "",
          updated_at: "",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    });
    const session = await createSession({
      duration_minutes: 20,
      difficulty: "hard",
      seniority: "senior",
    });
    expect(session.status).toBe("preparing");
    expect(session.id).toBe("11111111-1111-1111-1111-111111111111");
  });
});

describe("uploadDocument", () => {
  it("sends multipart form with doc_type and file", async () => {
    stubFetch((input, init) => {
      expect(String(input)).toContain("/sessions/s1/documents");
      expect(init?.method).toBe("POST");
      expect(init?.body).toBeInstanceOf(FormData);
      const form = init!.body as FormData;
      expect(form.get("doc_type")).toBe("resume");
      expect(form.get("file")).toBeInstanceOf(File);
      return new Response(
        JSON.stringify({
          id: "d1",
          user_id: "u1",
          doc_type: "resume",
          content_type: "text/plain",
          original_filename: "resume.txt",
          byte_size: 4,
          parse_status: "pending",
          parse_error: null,
          raw_text: null,
          r2_bucket: "b",
          r2_key: "k",
          created_at: "",
          updated_at: "",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    });
    const file = new File(["jane"], "resume.txt", { type: "text/plain" });
    const doc = await uploadDocument("s1", "resume", file);
    expect(doc.parse_status).toBe("pending");
  });
});

describe("pasteDocument", () => {
  it("posts json paste body", async () => {
    stubFetch((input, init) => {
      expect(String(input)).toContain("/sessions/s1/documents/paste");
      expect(JSON.parse(String(init?.body))).toEqual({
        doc_type: "jd",
        text: "Need Python",
      });
      return new Response(
        JSON.stringify({
          id: "d2",
          user_id: "u1",
          doc_type: "jd",
          content_type: "text/plain",
          original_filename: "jd.txt",
          byte_size: 11,
          parse_status: "pending",
          parse_error: null,
          raw_text: null,
          r2_bucket: "b",
          r2_key: "k",
          created_at: "",
          updated_at: "",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    });
    const doc = await pasteDocument("s1", "jd", "Need Python");
    expect(doc.doc_type).toBe("jd");
  });
});

describe("getSession / getDocument / startSession", () => {
  it("gets session by id", async () => {
    stubFetch((input) => {
      expect(String(input)).toContain("/sessions/s1");
      return new Response(
        JSON.stringify({
          id: "s1",
          user_id: "u1",
          status: "ready",
          settings: {},
          resume_document_id: "d1",
          jd_document_id: null,
          n_target: 4,
          lexicon: { skills: ["Python"] },
          created_at: "",
          updated_at: "",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    const session = await getSession("s1");
    expect(session.status).toBe("ready");
    expect(session.n_target).toBe(4);
  });

  it("gets document parse status", async () => {
    stubFetch((input) => {
      expect(String(input)).toContain("/documents/d1");
      return new Response(
        JSON.stringify({
          id: "d1",
          user_id: "u1",
          doc_type: "resume",
          content_type: "text/plain",
          original_filename: "resume.txt",
          byte_size: 10,
          parse_status: "ready",
          parse_error: null,
          raw_text: "Jane",
          r2_bucket: "b",
          r2_key: "k",
          created_at: "",
          updated_at: "",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    const doc = await getDocument("d1");
    expect(doc.parse_status).toBe("ready");
  });

  it("posts start and returns live session", async () => {
    stubFetch((input, init) => {
      expect(String(input)).toContain("/sessions/s1/start");
      expect(init?.method).toBe("POST");
      return new Response(
        JSON.stringify({
          id: "s1",
          user_id: "u1",
          status: "live",
          settings: {},
          resume_document_id: "d1",
          jd_document_id: null,
          n_target: 4,
          lexicon: {},
          started_at: "2026-09-29T12:00:00Z",
          ends_at: "2026-09-29T12:15:00Z",
          created_at: "",
          updated_at: "",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    const session = await startSession("s1");
    expect(session.status).toBe("live");
    expect(session.ends_at).toBe("2026-09-29T12:15:00Z");
  });

  it("posts answer and returns turns", async () => {
    const { answerSession } = await import("./api");
    stubFetch((input, init) => {
      expect(String(input)).toContain("/sessions/s1/answer");
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({ text: "I built caches" });
      return new Response(
        JSON.stringify({
          session: {
            id: "s1",
            user_id: "u1",
            status: "live",
            settings: {},
            resume_document_id: "d1",
            jd_document_id: null,
            n_target: 4,
            lexicon: {},
            started_at: "2026-09-29T12:00:00Z",
            ends_at: "2026-09-29T12:15:00Z",
            created_at: "",
            updated_at: "",
          },
          user_turn: {
            id: "tu",
            role: "user",
            raw_text: "I built caches",
            topic_id: "t1",
            frontier_node_id: "n1",
            created_at: "",
          },
          agent_turn: {
            id: "ta",
            role: "agent",
            raw_text: "What specifically?",
            topic_id: "t1",
            frontier_node_id: "n1",
            created_at: "",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    const out = await answerSession("s1", "I built caches");
    expect(out.agent_turn?.raw_text).toContain("specifically");
  });

  it("posts end and returns completed session", async () => {
    const { endSession } = await import("./api");
    stubFetch((input, init) => {
      expect(String(input)).toContain("/sessions/s1/end");
      expect(init?.method).toBe("POST");
      return new Response(
        JSON.stringify({
          id: "s1",
          user_id: "u1",
          status: "completed",
          settings: {},
          resume_document_id: "d1",
          jd_document_id: null,
          n_target: 4,
          lexicon: {},
          started_at: "2026-09-29T12:00:00Z",
          ends_at: "2026-09-29T12:15:00Z",
          created_at: "",
          updated_at: "",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    const session = await endSession("s1");
    expect(session.status).toBe("completed");
  });

  it("throws ApiError with detail on 409 start", async () => {
    stubFetch(
      () =>
        new Response(JSON.stringify({ detail: "session not ready (status=preparing)" }), {
          status: 409,
        }),
    );
    await expect(startSession("s1")).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "session not ready (status=preparing)",
    } satisfies Partial<ApiError>);
  });
});
