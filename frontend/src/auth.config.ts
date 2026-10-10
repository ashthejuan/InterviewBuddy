import type { NextAuthConfig } from "next-auth";
import { SESSION_MAX_AGE_SECONDS } from "@/lib/auth/session-config";

/**
 * Edge-safe Auth.js config (no Node fs/crypto).
 * Middleware imports this; Credentials + user store live in auth.ts.
 */
export const authConfig = {
  secret: process.env.AUTH_SECRET,
  session: {
    strategy: "jwt",
    maxAge: SESSION_MAX_AGE_SECONDS,
  },
  pages: {
    signIn: "/login",
  },
  providers: [],
  callbacks: {
    jwt({ token, user }) {
      if (user) {
        token.sub = user.id;
        token.email = user.email;
        token.name = user.name;
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        session.user.id = token.sub ?? "";
        if (token.email) session.user.email = token.email as string;
        if (token.name !== undefined) {
          session.user.name = token.name as string | null;
        }
      }
      return session;
    },
  },
  trustHost: true,
} satisfies NextAuthConfig;
