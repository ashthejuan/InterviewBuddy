import { AuthError, createUser } from "@/lib/auth/users";

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
  const name = typeof record.name === "string" ? record.name : null;

  try {
    const user = await createUser({ email, password, name });
    return Response.json(user, { status: 201 });
  } catch (err) {
    if (err instanceof AuthError) {
      return Response.json({ error: err.message }, { status: err.status });
    }
    throw err;
  }
}
