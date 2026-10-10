import { describe, expect, it } from "vitest";
import { logoutOptions } from "./logout";

describe("logoutOptions", () => {
  it("sends the user back to the login screen", () => {
    expect(logoutOptions()).toEqual({ callbackUrl: "/login" });
  });
});
