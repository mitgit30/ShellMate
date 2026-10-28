import { AgentMonitor } from "@/components/agent-monitor";

type MonitorPageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function MonitorPage({ searchParams }: MonitorPageProps) {
  const params = await searchParams;
  const value = params.server_id;
  const serverId = Array.isArray(value) ? value[0] ?? "" : value ?? "";
  return <AgentMonitor initialServerId={serverId} />;
}
