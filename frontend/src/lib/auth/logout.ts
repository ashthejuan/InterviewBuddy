/** Options for Auth.js `signOut` after the user leaves a session. */
export function logoutOptions() {
  return { callbackUrl: "/login" as const };
}
