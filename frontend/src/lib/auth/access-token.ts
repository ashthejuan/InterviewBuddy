import { SignJWT } from "jose";
import { SESSION_MAX_AGE_SECONDS } from "@/lib/auth/session-config";

const API_ISSUER = "interviewbuddy";
const API_AUDIENCE = "interviewbuddy-api";

function authSecretKey(): Uint8Array {
  const secret = process.env.AUTH_SECRET;
  if (!secret) {
    throw new Error("AUTH_SECRET is not configured");
  }
  return new TextEncoder().encode(secret);
}

/** HS256 Bearer token FastAPI verifies (same AUTH_SECRET as Auth.js). */
export async function mintApiAccessToken(input: {
  userId: string;
  email?: string | null;
}): Promise<{ token: string; expiresAt: string }> {
  const expiresAt = new Date(Date.now() + SESSION_MAX_AGE_SECONDS * 1000);
  const jwt = new SignJWT(
    input.email ? { email: input.email } : {},
  )
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(input.userId)
    .setIssuer(API_ISSUER)
    .setAudience(API_AUDIENCE)
    .setIssuedAt()
    .setExpirationTime(expiresAt);

  const token = await jwt.sign(authSecretKey());
  return { token, expiresAt: expiresAt.toISOString() };
}
