const AUTH_PAGES = new Set(["/login", "/signup"]);

export type AuthGateResult =
  | { action: "allow" }
  | { action: "redirect"; to: "/login" | "/" };

export function resolveAuthGate(input: {
  pathname: string;
  isAuthenticated: boolean;
}): AuthGateResult {
  const { pathname, isAuthenticated } = input;
  const onAuthPage = AUTH_PAGES.has(pathname);

  if (!isAuthenticated) {
    if (onAuthPage) return { action: "allow" };
    return { action: "redirect", to: "/login" };
  }

  if (onAuthPage) {
    return { action: "redirect", to: "/" };
  }

  return { action: "allow" };
}
