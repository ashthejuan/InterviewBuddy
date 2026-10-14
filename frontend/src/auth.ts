import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import GitHub from "next-auth/providers/github";
import { authConfig } from "@/auth.config";
import { linkOrCreateGithubUser } from "@/lib/auth/github-link";
import { AuthError, verifyUserCredentials } from "@/lib/auth/users";

const githubConfigured =
  Boolean(process.env.AUTH_GITHUB_ID) && Boolean(process.env.AUTH_GITHUB_SECRET);

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      authorize: async (credentials) => {
        const email = credentials?.email;
        const password = credentials?.password;
        if (typeof email !== "string" || typeof password !== "string") {
          return null;
        }
        const user = await verifyUserCredentials(email, password);
        if (!user) {
          return null;
        }
        return {
          id: user.id,
          email: user.email,
          name: user.name,
        };
      },
    }),
    ...(githubConfigured
      ? [
          GitHub({
            clientId: process.env.AUTH_GITHUB_ID!,
            clientSecret: process.env.AUTH_GITHUB_SECRET!,
            authorization: { params: { scope: "read:user user:email" } },
          }),
        ]
      : []),
  ],
  callbacks: {
    ...authConfig.callbacks,
    async signIn({ user, account }) {
      if (account?.provider === "github") {
        if (!user.email) {
          return "/login?error=EmailRequired";
        }
        try {
          const linked = await linkOrCreateGithubUser({
            githubId: account.providerAccountId,
            email: user.email,
            name: user.name ?? null,
          });
          user.id = linked.id;
          user.email = linked.email;
          user.name = linked.name;
        } catch (err) {
          if (err instanceof AuthError && err.code === "GITHUB_CONFLICT") {
            return "/login?error=GithubConflict";
          }
          return "/login?error=GithubLinkFailed";
        }
      }
      return true;
    },
    async jwt({ token, user, account }) {
      if (account?.provider === "github" && account.providerAccountId) {
        const linked = await linkOrCreateGithubUser({
          githubId: account.providerAccountId,
          email: user?.email ?? (token.email as string | undefined) ?? "",
          name: (user?.name as string | null | undefined) ?? null,
        });
        token.sub = linked.id;
        token.email = linked.email;
        token.name = linked.name;
        return token;
      }
      if (user) {
        token.sub = user.id;
        token.email = user.email;
        token.name = user.name;
      }
      return token;
    },
  },
});
