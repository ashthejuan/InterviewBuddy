import { NextResponse, type NextRequest } from "next/server";
import { resolveAuthGate } from "@/lib/auth/gate";

function isAuthApiPath(pathname: string): boolean {
  return (
    pathname.startsWith("/api/auth") ||
    pathname === "/api/signup" ||
    pathname === "/api/login" ||
    pathname === "/api/access-token"
  );
}

/** POST rewrites + session gate (no NextAuth import — unit-testable). */
export function applyAuthMiddleware(
  request: NextRequest,
  isAuthenticated: boolean,
): NextResponse {
  const { pathname } = request.nextUrl;

  if (request.method === "POST") {
    if (pathname === "/signup") {
      return NextResponse.rewrite(new URL("/api/signup", request.url));
    }
    if (pathname === "/login") {
      return NextResponse.rewrite(new URL("/api/login", request.url));
    }
  }

  if (isAuthApiPath(pathname)) {
    return NextResponse.next();
  }

  const gate = resolveAuthGate({ pathname, isAuthenticated });
  if (gate.action === "redirect") {
    return NextResponse.redirect(new URL(gate.to, request.url));
  }

  return NextResponse.next();
}
