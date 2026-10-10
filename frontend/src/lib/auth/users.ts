import { randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
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

type UsersFile = { users: StoredUser[] };

let cache: UsersFile | null = null;
let cachePath: string | null = null;

function usersPath(): string {
  return (
    process.env.AUTH_USERS_PATH ??
    path.join(process.cwd(), ".data", "auth-users.json")
  );
}

function load(): UsersFile {
  const filePath = usersPath();
  if (cache && cachePath === filePath) {
    return cache;
  }
  if (!existsSync(filePath)) {
    cache = { users: [] };
    cachePath = filePath;
    return cache;
  }
  const raw = readFileSync(filePath, "utf8");
  cache = JSON.parse(raw) as UsersFile;
  cachePath = filePath;
  return cache;
}

function save(data: UsersFile): void {
  const filePath = usersPath();
  mkdirSync(path.dirname(filePath), { recursive: true });
  writeFileSync(filePath, JSON.stringify(data, null, 2), "utf8");
  cache = data;
  cachePath = filePath;
}

export function resetUsersStoreForTests(): void {
  cache = null;
  cachePath = null;
}

function toPublic(user: StoredUser): PublicUser {
  return { id: user.id, email: user.email, name: user.name };
}

export async function findUserByEmail(
  email: string,
): Promise<StoredUser | null> {
  const normalized = email.trim().toLowerCase();
  return load().users.find((u) => u.email === normalized) ?? null;
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

  const user: StoredUser = {
    id: randomUUID(),
    email,
    name: input.name?.trim() || null,
    passwordHash: await hashPassword(input.password),
    createdAt: new Date().toISOString(),
  };

  const data = load();
  data.users.push(user);
  save(data);
  return toPublic(user);
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
