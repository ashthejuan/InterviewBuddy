import { auth } from "@/auth";
import { mintApiAccessToken } from "@/lib/auth/access-token";
import { clientIp } from "@/lib/auth/client-ip";
import { accessTokenLimiter } from "@/lib/auth/rate-limit";

export async function GET(request: Request): Promise<Response> {
  const session = await auth();
  const key = session?.user?.id
    ? `token:user:${session.user.id}`
    : `token:ip:${clientIp(request)}`;
  const limited = accessTokenLimiter.check(key);
  if (!limited.ok) {
    return Response.json(
      { error: "Too many token requests — try again shortly." },
      {
        status: 429,
        headers: { "Retry-After": String(limited.retryAfterSeconds) },
      },
    );
  }

  if (!session?.user?.id) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const grant = await mintApiAccessToken({
      userId: session.user.id,
      email: session.user.email,
    });
    return Response.json(grant);
  } catch {
    return Response.json(
      { error: "AUTH_SECRET is not configured" },
      { status: 503 },
    );
  }
}
