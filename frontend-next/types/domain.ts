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
  // The history API does not retain tool events, so retries are confirmed conservatively.
  mayRepeatCommand?: boolean;
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
};

export type MonitorTask = {
  task_id: string;
  session_id: string;
  server_id: string;
  user_request: string;
  status: "running" | "completed" | "failed" | string;
  current_skill: string | null;
  current_step: string | null;
  deployment_status: string;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
};

export type MonitorEvent = {
  event_id: number;
  task_id: string;
  event_type: string;
  detail: string | null;
  skill_id: string | null;
  step: string | null;
  tool_name: string | null;
  command: string | null;
  iteration: number | null;
  exit_status: number | null;
  created_at: string;
};

export type MonitorTaskDetails = {
  task: MonitorTask;
  events: MonitorEvent[];
};
