import { API_BASE, getHealth } from "@/lib/api";

export default async function Home() {
  let apiStatus = "unreachable";
  try {
    const health = await getHealth();
    apiStatus = health.status;
  } catch {
    apiStatus = "unreachable";
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-6">
      <h1 className="text-3xl font-semibold tracking-tight">InterviewBuddy</h1>
      <p className="text-neutral-600">
        Phase 0 shell — upload, grill, and debrief land in later phases.
      </p>
      <p className="font-mono text-sm text-neutral-500">
        API ({API_BASE}): {apiStatus}
      </p>
    </main>
  );
}
