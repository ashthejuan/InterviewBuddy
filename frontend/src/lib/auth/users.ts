import { randomUUID } from "node:crypto";
import { Pool, type PoolClient, type QueryResult } from "pg";
import { hashPassword, validatePassword, verifyPassword } from "./password";

export type StoredUser = {
  id: string;
  email: string;
  name: string | null;
  passwordHash: string;
  createdAt: string;
};

export type PublicUser = {
  id: string;
  email: string;
  name: string | null;
};

export class AuthError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

let pool: Pool | null = null;

/** Convert SQLAlchemy/asyncpg URLs to node-pg connection strings. */
export function syncDatabaseUrl(raw?: string): string {
  const url =
    raw ??
    process.env.DATABASE_URL ??
    process.env.POSTGRES_URL ??
    "postgresql://interviewbuddy:interviewbuddy@localhost:5432/interviewbuddy";
  return url
    .replace(/^postgresql\+asyncpg:/, "postgresql:")
    .replace(/^postgresql\+psycopg:/, "postgresql:")
    .replace(/^postgres:/, "postgresql:");
}

function getPool(): Pool {
  if (!pool) {
    pool = new Pool({ connectionString: syncDatabaseUrl() });
  }
  return pool;
}

export async function resetUsersStoreForTests(): Promise<void> {
  if (pool) {
    await pool.end().catch(() => undefined);
    pool = null;
  }
}

export async function deleteUsersByEmailsForTests(
  emails: string[],
): Promise<void> {
  if (emails.length === 0) return;
  const normalized = emails.map((e) => e.trim().toLowerCase());
  await getPool().query("DELETE FROM users WHERE email = ANY($1::text[])", [
    normalized,
  ]);
}

function rowToStored(row: {
  id: string;
  email: string;
  name: string | null;
  password_hash: string | null;
  created_at: Date | string;
}): StoredUser | null {
  if (!row.password_hash) return null;
  const createdAt =
    row.created_at instanceof Date
      ? row.created_at.toISOString()
      : String(row.created_at);
  return {
    id: row.id,
    email: row.email,
    name: row.name,
    passwordHash: row.password_hash,
    createdAt,
  };
}

function toPublic(user: StoredUser): PublicUser {
  return { id: user.id, email: user.email, name: user.name };
}

export async function findUserByEmail(
  email: string,
): Promise<StoredUser | null> {
  const normalized = email.trim().toLowerCase();
  const result: QueryResult = await getPool().query(
    `SELECT id::text, email, name, password_hash, created_at
     FROM users WHERE email = $1`,
    [normalized],
  );
  if (result.rowCount === 0) return null;
  return rowToStored(result.rows[0]);
}

export async function createUser(input: {
  email: string;
  password: string;
  name?: string | null;
}): Promise<PublicUser> {
  const email = input.email.trim().toLowerCase();
  if (!email || !email.includes("@")) {
    throw new AuthError("INVALID_EMAIL", "Valid email is required", 400);
  }

  const passwordCheck = validatePassword(input.password);
  if (!passwordCheck.ok) {
    throw new AuthError("WEAK_PASSWORD", passwordCheck.error, 400);
  }

  const existing = await findUserByEmail(email);
  if (existing) {
    throw new AuthError("EMAIL_TAKEN", "Email already registered", 409);
  }

  const id = randomUUID();
  const passwordHash = await hashPassword(input.password);
  const name = input.name?.trim() || null;

  try {
    await getPool().query(
      `INSERT INTO users (id, email, name, password_hash)
       VALUES ($1::uuid, $2, $3, $4)`,
      [id, email, name, passwordHash],
    );
  } catch (err) {
    const code =
      err && typeof err === "object" && "code" in err
        ? String((err as { code: unknown }).code)
        : "";
    if (code === "23505") {
      throw new AuthError("EMAIL_TAKEN", "Email already registered", 409);
    }
    throw err;
  }

  return { id, email, name };
}

export async function verifyUserCredentials(
  email: string,
  password: string,
): Promise<PublicUser | null> {
  const user = await findUserByEmail(email);
  if (!user) {
    return null;
  }
  const ok = await verifyPassword(password, user.passwordHash);
  if (!ok) {
    return null;
  }
  return toPublic(user);
}

/** Exposed for rare transactional helpers / tests. */
export async function withClient<T>(
  fn: (client: PoolClient) => Promise<T>,
): Promise<T> {
  const client = await getPool().connect();
  try {
    return await fn(client);
  } finally {
    client.release();
  }
}
