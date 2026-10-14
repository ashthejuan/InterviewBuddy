import { auth } from "@/auth";
import { mintApiAccessToken } from "@/lib/auth/access-token";

export async function GET(): Promise<Response> {
  const session = await auth();
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
