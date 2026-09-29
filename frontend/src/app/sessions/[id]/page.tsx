import { LiveInterview } from "@/components/LiveInterview";

export default async function SessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <LiveInterview sessionId={id} />;
}
