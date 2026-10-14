"use client";

import Link from "next/link";
import { signIn } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { userMessageForStatus } from "@/lib/retry";

function GitHubMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
    >
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58 0-.28-.01-1.02-.02-2-3.34.73-4.04-1.61-4.04-1.61-.55-1.38-1.33-1.75-1.33-1.75-1.09-.74.08-.73.08-.73 1.2.09 1.84 1.24 1.84 1.24 1.07 1.83 2.8 1.3 3.49.99.11-.78.42-1.3.76-1.6-2.66-.3-5.46-1.33-5.46-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 3-.4c1.02 0 2.05.14 3 .4 2.28-1.55 3.29-1.23 3.29-1.23.66 1.66.24 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.8 5.62-5.47 5.92.43.37.81 1.1.81 2.22 0 1.6-.01 2.89-.01 3.28 0 .32.22.7.83.58C20.56 21.8 24 17.3 24 12 24 5.37 18.63 0 12 0z" />
    </svg>
  );
}

type Mode = "signup" | "login";

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [githubPending, setGithubPending] = useState(false);

  const oauthError = useMemo(() => {
    const code = searchParams.get("error");
    if (code === "EmailRequired") {
      return "GitHub did not share an email. Make your GitHub email visible, or use password signup.";
    }
    if (code === "GithubConflict") {
      return "This email is already linked to a different GitHub account.";
    }
    if (code === "Configuration" || code === "OAuthSignin") {
      return "GitHub sign-in is not configured. Set AUTH_GITHUB_ID and AUTH_GITHUB_SECRET in frontend/.env.local (or root .env), then restart Next.js.";
    }
    if (
      code === "GithubLinkFailed" ||
      code === "OAuthAccountNotLinked" ||
      code === "Callback"
    ) {
      return "Could not complete GitHub sign-in. Try again or use email and password.";
    }
    return null;
  }, [searchParams]);

  async function onGithub() {
    setError(null);
    setGithubPending(true);
    try {
      const result = await signIn("github", {
        callbackUrl: "/",
        redirect: false,
      });
      if (result?.error) {
        setError(
          result.error === "Configuration" || result.error === "OAuthSignin"
            ? "GitHub sign-in is not configured. Set AUTH_GITHUB_ID and AUTH_GITHUB_SECRET in frontend/.env.local (or root .env), then restart Next.js."
            : "GitHub sign-in failed — try again",
        );
        setGithubPending(false);
        return;
      }
      if (result?.url) {
        window.location.assign(result.url);
        return;
      }
      setError("GitHub sign-in failed — try again");
      setGithubPending(false);
    } catch {
      setError("GitHub sign-in failed — try again");
      setGithubPending(false);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);

    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");
    const name = String(form.get("name") ?? "");

    try {
      if (mode === "signup") {
        const signupRes = await fetch("/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, name: name || undefined }),
        });
        const signupData = (await signupRes.json()) as { error?: string };
        if (!signupRes.ok) {
          setError(
            signupRes.status === 429
              ? userMessageForStatus(429, signupData.error ?? "Sign up failed")
              : (signupData.error ?? "Sign up failed"),
          );
          return;
        }
      } else {
        const loginRes = await fetch("/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        const loginData = (await loginRes.json()) as { error?: string };
        if (!loginRes.ok) {
          setError(
            loginRes.status === 429
              ? userMessageForStatus(429, loginData.error ?? "Login failed")
              : (loginData.error ?? "Invalid email or password"),
          );
          return;
        }
      }

      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
      });

      if (result?.error) {
        setError(
          mode === "signup"
            ? "Account created, but sign-in failed — try logging in"
            : "Invalid email or password",
        );
        return;
      }

      router.push("/");
      router.refresh();
    } catch {
      setError("Network error — try again");
    } finally {
      setPending(false);
    }
  }

  const displayError = error ?? oauthError;

  return (
    <main className="auth-shell flex min-h-dvh w-full items-center justify-center px-4 py-12 sm:px-6">
      <div
        data-testid="auth-panel"
        className="w-full max-w-md rounded-xl border border-border bg-card px-8 py-10 text-card-foreground shadow-[0_1px_2px_rgba(16,19,33,0.04),0_12px_40px_rgba(16,19,33,0.08)] sm:px-10"
      >
        <p className="font-[family-name:var(--font-display)] text-sm font-semibold tracking-wide text-[var(--brand)]">
          InterviewBuddy
        </p>
        <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight text-foreground">
          {mode === "signup" ? "Create account" : "Log in"}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {mode === "signup"
            ? "Sign up with email and password or GitHub to start practicing."
            : "Welcome back — email and password or GitHub."}
        </p>

        <div className="mt-8 space-y-3">
          <Button
            type="button"
            variant="outline"
            className="w-full gap-2"
            disabled={pending || githubPending}
            onClick={onGithub}
          >
            <GitHubMark className="size-4 shrink-0" />
            {githubPending ? "Redirecting…" : "Continue with GitHub"}
          </Button>
          <div className="relative py-1 text-center text-xs text-muted-foreground">
            <span className="bg-card px-2 relative z-10">or</span>
            <span className="absolute inset-x-0 top-1/2 h-px bg-border" />
          </div>
        </div>

        <form onSubmit={onSubmit} className="mt-2 space-y-4">
          {mode === "signup" ? (
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" name="name" type="text" autoComplete="name" />
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              required
              minLength={8}
            />
          </div>

          {displayError ? (
            <p className="text-sm text-destructive" role="alert">
              {displayError}
            </p>
          ) : null}

          <Button type="submit" className="w-full" disabled={pending || githubPending}>
            {pending ? "Please wait…" : mode === "signup" ? "Sign up" : "Log in"}
          </Button>
        </form>

        <p className="mt-6 text-sm text-muted-foreground">
          {mode === "signup" ? (
            <>
              Already have an account?{" "}
              <Link href="/login" className="text-[var(--link)] underline-offset-4 hover:underline">
                Log in
              </Link>
            </>
          ) : (
            <>
              Need an account?{" "}
              <Link href="/signup" className="text-[var(--link)] underline-offset-4 hover:underline">
                Sign up
              </Link>
            </>
          )}
        </p>
      </div>
    </main>
  );
}
