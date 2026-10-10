import bcrypt from "bcryptjs";

const MIN_LENGTH = 8;

export type PasswordValidation =
  | { ok: true }
  | { ok: false; error: string };

export function validatePassword(password: string): PasswordValidation {
  if (password.length < MIN_LENGTH) {
    return { ok: false, error: "Password must be at least 8 characters" };
  }
  return { ok: true };
}

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, 12);
}

export async function verifyPassword(
  password: string,
  passwordHash: string,
): Promise<boolean> {
  return bcrypt.compare(password, passwordHash);
}
