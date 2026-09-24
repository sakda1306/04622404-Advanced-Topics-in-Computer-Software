/** Mirrors 02_api_backend's OpenAPI schema (components/schemas). Keep in sync by hand. */

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type RecommendationType = "TRAVEL_NORMALLY" | "CHANGE_ROUTE" | "DELAY_TRAVEL" | "AVOID_TRAVEL";
export type RecommendationStatus =
  | "processing"
  | "completed"
  | "partial_result"
  | "needs_clarification"
  | "failed"
  | "cancelled";
export type ServiceState = "ok" | "degraded" | "unavailable" | "not_used";
export type DataCategory = "WEATHER" | "TRANSPORT" | "DISASTER" | "KNOWLEDGE_BASE";
export type TravelMode = "CAR" | "TRAIN" | "BUS" | "FLIGHT" | "FERRY" | "WALK" | "BICYCLE";
export type AvoidOption = "TOLLS" | "HIGHWAYS" | "FERRIES" | "NIGHT_TRAVEL";

export type Location = {
  lat: number;
  lon: number;
  name?: string | null;
  place_id?: string | null;
};

export type Preferences = {
  travel_modes?: TravelMode[];
  avoid?: AvoidOption[];
  max_travel_hours?: number | null;
  mobility_needs?: string[];
  traveler_count?: number;
};

export type TravelRequest = {
  origin: Location;
  destination: Location;
  waypoints?: Location[];
  departure_time: string;
  timezone: string;
  language?: string | null;
  preferences?: Preferences;
  question?: string | null;
  conversation_id?: string | null;
  trip_id?: string | null;
};

export type RiskFactor = {
  type: string;
  level: RiskLevel;
  description: string;
};

export type Risk = {
  level: RiskLevel;
  score: number | null;
  confidence: number | null;
  factors: RiskFactor[];
};

export type RecommendationBody = {
  type: RecommendationType | null;
  summary: string | null;
  reasons: string[];
  suggested_departure_time: string | null;
};

export type RouteLeg = {
  mode: string;
  from: string | null;
  to: string | null;
  departure_at: string | null;
  arrival_at: string | null;
  operator: string | null;
  service_status: string | null;
};

export type RouteGeometry = { type: string; coordinates: unknown };

export type RouteOption = {
  route_id: string;
  label: string | null;
  travel_modes: string[];
  distance_km: number | null;
  duration_minutes: number | null;
  risk_level: RiskLevel | null;
  geometry: RouteGeometry | null;
  legs: RouteLeg[];
  restrictions: string[];
  tips: string[];
};

export type Routes = {
  primary: RouteOption | null;
  alternatives: RouteOption[];
};

export type Hazard = {
  hazard_id: string;
  type: string;
  severity: RiskLevel;
  title: string;
  area: Record<string, unknown> | null;
  starts_at: string | null;
  ends_at: string | null;
  source_id: string | null;
};

export type EmergencyContact = {
  name: string;
  phone: string;
  url?: string | null;
  available_hours?: string | null;
};

export type SupportPlace = {
  name: string;
  type: string;
  location: { type: string; coordinates: [number, number] } | null;
};

export type EmergencyInstructions = {
  what_to_do_now: string;
  safety_steps: string[];
  contacts: EmergencyContact[];
  nearest_support: SupportPlace[];
};

export type SourceItem = {
  source_id: string;
  name: string;
  category: DataCategory;
  url: string | null;
  retrieved_at: string | null;
};

export type FreshnessItem = {
  category: DataCategory;
  updated_at: string | null;
  age_seconds: number | null;
  is_stale: boolean;
};

export type DataFreshness = {
  overall_is_stale: boolean;
  items: FreshnessItem[];
};

export type WarningItem = { code: string; message: string };

export type Versions = {
  api: string;
  agent: string | null;
  risk_model: string | null;
  prompt: string | null;
};

export type Clarification = {
  question: string;
  missing_fields: string[];
  options: string[] | null;
};

export type ErrorInfo = { code: string; message: string };

export type RecommendationResponse = {
  recommendation_id: string;
  conversation_id: string | null;
  request_id: string;
  status: RecommendationStatus;
  created_at: string;
  valid_until?: string | null;
  language?: string | null;
  risk: Risk | null;
  recommendation: RecommendationBody | null;
  routes: Routes | null;
  hazards: Hazard[];
  emergency_instructions: EmergencyInstructions | null;
  sources: SourceItem[];
  data_freshness: DataFreshness | null;
  service_status: Record<string, ServiceState>;
  clarification: Clarification | null;
  warnings: WarningItem[];
  versions?: Versions | null;
  disclaimer?: string | null;
  job_id?: string | null;
  error?: ErrorInfo | null;
};

export type JobAccepted = {
  job_id: string;
  status: "queued";
  recommendation_id: string;
  conversation_id: string;
  events_url: string;
  status_url: string;
  estimated_seconds?: number;
};

export function isJobAccepted(
  value: RecommendationResponse | JobAccepted,
): value is JobAccepted {
  return (value as JobAccepted).status === "queued" && "events_url" in value;
}

export type FeedbackCreate = {
  rating?: number | null;
  helpful?: boolean | null;
  outcome?: "UNKNOWN" | "FOLLOWED" | "PARTIALLY_FOLLOWED" | "IGNORED";
  report_type?: "INACCURATE" | "OUTDATED" | "UNSAFE" | "OTHER" | null;
  comment?: string | null;
};

export type FeedbackCreated = {
  feedback_id: string;
  created_at: string;
  review_status: string;
};

/** Legacy alias kept so any lingering imports keep compiling. */
export type Recommendation = RecommendationResponse;

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type JobStage = "queued" | "retrieval" | "synthesis" | "safety_gate" | "completed" | "failed";
export type JobType = "RECOMMENDATION" | "REEVALUATION" | "TRAINING_EXPORT";

export type AdminJob = {
  job_id: string;
  type: JobType;
  status: JobStatus;
  stage: JobStage;
  attempts: number;
  error_code: string | null;
  recommendation_id: string | null;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AdminJobPage = {
  items: AdminJob[];
  next_cursor: string | null;
};

export type AgentRunStatus = "running" | "success" | "failure" | "timeout";

export type AgentRun = {
  run_id: string;
  attempt: number;
  status: AgentRunStatus;
  http_status: number | null;
  error_code: string | null;
  duration_ms: number | null;
  tool_calls: number | null;
  agent_version: string | null;
  trace_id: string | null;
  started_at: string;
  finished_at: string | null;
};

export type AdminRecommendation = {
  recommendation_id: string;
  source: string;
  status: RecommendationStatus;
  risk_level: RiskLevel | null;
  risk_score: number | null;
  risk_confidence: number | null;
  recommendation_type: RecommendationType | null;
  warning_codes: string[];
  safety_gate_rules: string[];
  overall_is_stale: boolean | null;
  error_code: string | null;
  versions: Record<string, string | null>;
  data_freshness: Array<{
    category: DataCategory;
    updated_at: string | null;
    age_seconds: number | null;
    is_stale: boolean;
  }>;
  service_status: Record<string, string>;
  created_at: string;
  completed_at: string | null;
  valid_until: string | null;
  job: AdminJob | null;
  agent_runs: AgentRun[];
};

export type ReviewStatus = "not_required" | "pending" | "approved" | "rejected";
export type ReviewDecision = "approved" | "rejected";

export type ReviewResponse = {
  feedback_id: string;
  recommendation_id: string;
  rating: number | null;
  helpful: boolean | null;
  outcome: string;
  report_type: string | null;
  comment: string | null;
  review_status: ReviewStatus;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
};

export type ReviewQueueItem = ReviewResponse & {
  recommendation: Record<string, unknown> | null;
};

export type ReviewPage = {
  items: ReviewQueueItem[];
  next_cursor: string | null;
};

export type ReviewUpdate = {
  status: ReviewDecision;
  note?: string | null;
};

export type ActorType = "user" | "admin" | "service" | "system";
export type AuditResult = "success" | "denied" | "error";

export type AuditLogItem = {
  id: number;
  occurred_at: string;
  actor_type: ActorType;
  actor_ref: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  result: AuditResult;
  correlation_id: string;
  metadata: Record<string, unknown>;
};

export type AuditLogPage = {
  items: AuditLogItem[];
  next_cursor: string | null;
};

export type ExportStatus = "queued" | "running" | "completed" | "failed";

export type TrainingExportRequest = {
  from?: string | null;
  to?: string | null;
};

export type TrainingExportAccepted = {
  export_id: string;
  status: ExportStatus;
};

export type TrainingExportResponse = {
  export_id: string;
  status: ExportStatus;
  from: string;
  to: string;
  row_count: number | null;
  created_at: string;
  completed_at: string | null;
  expires_at: string | null;
  download_url: string | null;
};

