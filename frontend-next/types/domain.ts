export type AuthMode = "login" | "register";

export type AuthResult = {
  access_token: string;
  email: string;
  user_id: string;
  expires_in: number;
};

export type CurrentUser = {
  token: string;
  email: string;
};

export type Server = {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  key_id: string;
};

export type ChatSession = {
  session_id: string;
  server_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  createdAt?: string;
  id?: string;
  error?: string;
  failed?: boolean;
  commandBlocks?: ChatCommandBlock[];
};

export type CommandRisk = "read-only" | "controlled" | "destructive";

export type ChatCommandBlock = {
  id: string;
  command: string;
  risk: CommandRisk;
  output: string;
  status: "running" | "completed" | "failed" | "interrupted";
  exitStatus?: number;
};

export type ChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type StreamEvent = {
  type?: string;
  content?: string;
  detail?: string;
  tool_name?: string;
  step?: string;
  command?: string;
  iteration?: number;
  stdout?: string;
  stderr?: string;
  exit_status?: number;
};
