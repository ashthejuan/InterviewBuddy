"use client";

import Link from "next/link";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Mode = "signup" | "login";

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

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
          setError(signupData.error ?? "Sign up failed");
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
          setError(loginData.error ?? "Invalid email or password");
          return;
        }
      }

      // Auth.js Credentials provider — sets the session cookie.
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
            ? "Sign up with email and password to start practicing."
            : "Welcome back — enter your email and password."}
        </p>

        <form onSubmit={onSubmit} className="mt-8 space-y-4">
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

          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}

          <Button type="submit" className="w-full" disabled={pending}>
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
