"use client";

import { signOut } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { logoutOptions } from "@/lib/auth/logout";

export function LogoutButton() {
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => {
        void signOut(logoutOptions());
      }}
    >
      Log out
    </Button>
  );
}
