import NextAuth from "next-auth";
import { authConfig } from "@/auth.config";
import { applyAuthMiddleware } from "@/lib/auth/middleware-handler";

const { auth } = NextAuth(authConfig);

export default auth((request) => {
  return applyAuthMiddleware(request, !!request.auth);
});

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
