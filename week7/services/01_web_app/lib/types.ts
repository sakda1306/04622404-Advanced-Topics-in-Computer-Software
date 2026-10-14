export type User = {
  id: string;
  username: string;
  display_name: string;
  role: "user" | "admin";
  favorite_team_id: number | null;
  language: "th" | "en";
};
export type Source = {
  ref: number;
  doc_id?: string;
  title: string;
  category?: string | null;
  origin?: string | null;
  fetched_at?: string | null;
  url?: string | null;
};
export type Trace = {
  decided_at_layer?: string | null;
  intent?: string | null;
  rewritten_query?: string | null;
  standalone_query?: string | null;
  condense?: "applied" | "unchanged" | "rejected" | "unavailable" | null;
  filters?: Record<string, unknown> | null;
  fallback?: string | null;
  steps?: { name: string; ms: number }[];
};
export type Route =
  | "football_rag"
  | "general_ai"
  | "local_ai"
  | "clarify"
  | "decline"
  | "chat";
export const routeLabels: Record<Route, string> = {
  football_rag: "ตอบจากคลังข้อมูลฟุตบอล",
  general_ai: "ความรู้ทั่วไป",
  local_ai: "โมเดลทำนาย",
  clarify: "ขอข้อมูลเพิ่ม",
  decline: "นอกขอบเขต",
  chat: "คุยกับผู้ช่วย",
};
export type ChatEntry = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  data_as_of?: string | null;
  route?: Route | null;
  latency_ms?: number | null;
  trace?: Trace | null;
  rating?: number | null;
  created_at?: string;
};
export type ChatResult = {
  request_id: string;
  session_id: string;
  message_id: string;
  answer: string;
  sources: Source[];
  data_as_of: string | null;
  route: Route;
  latency_ms: number;
  trace?: Trace | null;
  created_at: string;
};
export type Session = { session_id: string; title: string; updated_at: string };
export type Page<T> = { items: T[]; next_cursor: string | null };
export type FootballStatus = {
  total_matchweeks?: number | null;
  current_season: string;
  current_matchweek: number;
  last_ingest_at: string | null;
  quota: {
    api_football_used_today: number;
    api_football_limit: number;
    reset_at?: string;
  };
};
export type Standing = {
  position: number;
  team_id: number;
  name: string;
  played: number;
  won: number;
  draw: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
  form: string | null;
};
export type Match = {
  venue?: { name: string } | null;
  match_id: string;
  season: string;
  matchweek: number;
  kickoff: string;
  status: string;
  home: { team_id: number; name: string };
  away: { team_id: number; name: string };
  score: { home: number | null; away: number | null };
  events?:
    | { minute: number; type: string; player?: string; team_id?: number }[]
    | null;
  lineups?: unknown;
  statistics?: unknown;
  fetched_at?: string | null;
};
export type Report = {
  season: string;
  matchweek: number;
  title: string;
  markdown: string;
  status: "draft" | "published" | "unpublished";
  data_as_of?: string | null;
  generated_at?: string;
};
export type Job = {
  job_id: string;
  kind: string;
  scope?: string | null;
  status: "queued" | "running" | "done" | "failed";
  triggered_by?: string;
  started_at?: string;
  finished_at?: string | null;
  detail?: unknown;
};
export type Stats = {
  days: number;
  total_messages: number;
  by_route: Record<string, number>;
  by_layer: Record<string, number>;
  feedback: { up: number; down: number };
  latency_ms: { p50: number; p95: number };
  fallback_count: number;
};
export function dateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("th-TH", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Bangkok",
      }).format(date);
}
