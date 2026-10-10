import { describe, expect, it } from "vitest";
import { resolveAuthGate } from "./gate";

describe("resolveAuthGate", () => {
  it("sends unauthenticated users from / to /login", () => {
    expect(resolveAuthGate({ pathname: "/", isAuthenticated: false })).toEqual({
      action: "redirect",
      to: "/login",
    });
  });

  it("sends unauthenticated users from protected routes to /login", () => {
    expect(
      resolveAuthGate({
        pathname: "/sessions/abc",
        isAuthenticated: false,
      }),
    ).toEqual({ action: "redirect", to: "/login" });
  });

  it("allows unauthenticated access to login and signup pages", () => {
    expect(resolveAuthGate({ pathname: "/login", isAuthenticated: false })).toEqual({
      action: "allow",
    });
    expect(resolveAuthGate({ pathname: "/signup", isAuthenticated: false })).toEqual({
      action: "allow",
    });
  });

  it("allows authenticated users through the app", () => {
    expect(resolveAuthGate({ pathname: "/", isAuthenticated: true })).toEqual({
      action: "allow",
    });
  });

  it("sends authenticated users away from auth pages to /", () => {
    expect(resolveAuthGate({ pathname: "/login", isAuthenticated: true })).toEqual({
      action: "redirect",
      to: "/",
    });
    expect(resolveAuthGate({ pathname: "/signup", isAuthenticated: true })).toEqual({
      action: "redirect",
      to: "/",
    });
  });
});
