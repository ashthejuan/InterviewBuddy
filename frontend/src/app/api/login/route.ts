import { verifyUserCredentials } from "@/lib/auth/users";

export async function POST(request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const record = body as Record<string, unknown>;
  const email = typeof record.email === "string" ? record.email : "";
  const password = typeof record.password === "string" ? record.password : "";

  if (!email || !password) {
    return Response.json(
      { error: "Email and password are required" },
      { status: 400 },
    );
  }

  const user = await verifyUserCredentials(email, password);
  if (!user) {
    return Response.json({ error: "Invalid email or password" }, { status: 401 });
  }

  return Response.json({ ok: true, user });
}
