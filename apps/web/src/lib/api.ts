const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

export type ApiError = {
  detail: string | { msg: string; type: string }[];
};

export class ApiClientError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as ApiError;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => item.msg).join(", ");
    }
  } catch {
    // ignore parse errors
  }
  return response.statusText || "Request failed";
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_URL}${API_PREFIX}${path}`, {
    ...options,
    headers,
  }).catch(() => {
    throw new ApiClientError(
      `Cannot reach the API at ${API_URL}. Start it with uvicorn on port 8000.`,
      0,
    );
  });

  if (!response.ok) {
    throw new ApiClientError(await parseError(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  avatar_url: string | null;
  created_at: string;
  updated_at: string;
};

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export const authApi = {
  signup: (data: { email: string; password: string; full_name?: string }) =>
    apiFetch<User>("/auth/signup", { method: "POST", body: JSON.stringify(data) }),

  login: (data: { email: string; password: string }) =>
    apiFetch<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(data) }),

  refresh: (refresh_token: string) =>
    apiFetch<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token }),
    }),

  logout: (refresh_token: string, access_token: string) =>
    apiFetch<{ message: string }>(
      "/auth/logout",
      { method: "POST", body: JSON.stringify({ refresh_token }) },
      access_token,
    ),

  forgotPassword: (email: string) =>
    apiFetch<{ message: string }>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, new_password: string) =>
    apiFetch<{ message: string }>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password }),
    }),

  getProfile: (access_token: string) => apiFetch<User>("/users/me", {}, access_token),

  updateProfile: (
    data: { full_name?: string; avatar_url?: string },
    access_token: string,
  ) =>
    apiFetch<User>(
      "/users/me",
      { method: "PATCH", body: JSON.stringify(data) },
      access_token,
    ),
};

export type Organization = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  role: string | null;
  created_at: string;
  updated_at: string;
};

export type OrganizationMember = {
  id: string;
  user_id: string;
  email: string | null;
  full_name: string | null;
  role: string;
  created_at: string;
};

export type Project = {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type ApiKey = {
  id: string;
  project_id: string;
  name: string;
  key_prefix: string;
  last_used_at: string | null;
  revoked_at: string | null;
  is_revoked: boolean;
  created_at: string;
};

export type CreatedApiKey = ApiKey & { secret: string };

export const workspaceApi = {
  listOrganizations: (token: string) =>
    apiFetch<Organization[]>("/organizations", {}, token),

  createOrganization: (data: { name: string; description?: string }, token: string) =>
    apiFetch<Organization>("/organizations", { method: "POST", body: JSON.stringify(data) }, token),

  getOrganization: (orgId: string, token: string) =>
    apiFetch<Organization>(`/organizations/${orgId}`, {}, token),

  updateOrganization: (
    orgId: string,
    data: { name?: string; description?: string },
    token: string,
  ) =>
    apiFetch<Organization>(
      `/organizations/${orgId}`,
      { method: "PATCH", body: JSON.stringify(data) },
      token,
    ),

  listMembers: (orgId: string, token: string) =>
    apiFetch<OrganizationMember[]>(`/organizations/${orgId}/members`, {}, token),

  inviteMember: (orgId: string, data: { email: string; role: string }, token: string) =>
    apiFetch<OrganizationMember>(
      `/organizations/${orgId}/members`,
      { method: "POST", body: JSON.stringify(data) },
      token,
    ),

  listProjects: (orgId: string, token: string) =>
    apiFetch<Project[]>(`/organizations/${orgId}/projects`, {}, token),

  createProject: (
    orgId: string,
    data: { name: string; description?: string },
    token: string,
  ) =>
    apiFetch<Project>(
      `/organizations/${orgId}/projects`,
      { method: "POST", body: JSON.stringify(data) },
      token,
    ),

  getProject: (projectId: string, token: string) =>
    apiFetch<Project>(`/projects/${projectId}`, {}, token),

  updateProject: (
    projectId: string,
    data: { name?: string; description?: string },
    token: string,
  ) =>
    apiFetch<Project>(
      `/projects/${projectId}`,
      { method: "PATCH", body: JSON.stringify(data) },
      token,
    ),

  deleteProject: (projectId: string, token: string) =>
    apiFetch<void>(`/projects/${projectId}`, { method: "DELETE" }, token),

  listApiKeys: (projectId: string, token: string) =>
    apiFetch<ApiKey[]>(`/projects/${projectId}/api-keys`, {}, token),

  createApiKey: (projectId: string, name: string, token: string) =>
    apiFetch<CreatedApiKey>(
      `/projects/${projectId}/api-keys`,
      { method: "POST", body: JSON.stringify({ name }) },
      token,
    ),

  revokeApiKey: (projectId: string, keyId: string, token: string) =>
    apiFetch<ApiKey>(
      `/projects/${projectId}/api-keys/${keyId}/revoke`,
      { method: "POST" },
      token,
    ),
};

export type TraceSummary = {
  id: string;
  project_id: string;
  name: string;
  agent_name: string | null;
  session_id: string | null;
  status: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number | null;
  total_tokens: number;
  total_cost: string | number;
  error_message: string | null;
  agent_version: string | null;
  prompt_version: string | null;
  model_version: string | null;
};

export type LLMCall = {
  id: string;
  trace_id: string;
  span_id: string | null;
  provider: string;
  model: string;
  messages: unknown;
  completion: unknown;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  latency_ms: number | null;
  estimated_cost: string | number;
  temperature: number | null;
  metadata: unknown;
};

export type ToolCall = {
  id: string;
  trace_id: string;
  span_id: string | null;
  name: string;
  arguments: unknown;
  output: unknown;
  status: string;
  duration_ms: number | null;
  error: string | null;
  retry_count: number;
  metadata: unknown;
};

export type TraceSpan = {
  id: string;
  trace_id: string;
  parent_span_id: string | null;
  type: string;
  name: string;
  status: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number | null;
  input: unknown;
  output: unknown;
  metadata: unknown;
  error_type: string | null;
  error_message: string | null;
  llm_call: LLMCall | null;
  tool_call: ToolCall | null;
};

export type TraceEvent = {
  id: string;
  trace_id: string;
  span_id: string | null;
  name: string;
  body: unknown;
  timestamp: string;
};

export type TraceDetail = TraceSummary & {
  input: unknown;
  output: unknown;
  metadata: unknown;
  error_type: string | null;
  input_tokens: number;
  output_tokens: number;
  spans: TraceSpan[];
  events: TraceEvent[];
};

export const tracesApi = {
  list: (projectId: string, token: string) =>
    apiFetch<{ items: TraceSummary[]; total: number }>(
      `/projects/${projectId}/traces`,
      {},
      token,
    ),
  get: (traceId: string, token: string) =>
    apiFetch<TraceDetail>(`/traces/${traceId}`, {}, token),
};

export type AnalyticsSummary = {
  total_runs: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  error_rate: number;
  avg_latency_ms: number | null;
  total_tokens: number;
  total_cost: string | number;
};

export type TimeseriesPoint = {
  timestamp: string;
  runs: number;
  successes: number;
  errors: number;
  avg_latency_ms: number | null;
  tokens: number;
  cost: string | number;
};

export type ModelUsage = {
  model: string;
  provider: string;
  calls: number;
  tokens: number;
  cost: string | number;
  avg_latency_ms: number | null;
};

export type AnalyticsResponse = {
  range: string;
  start: string;
  end: string;
  grain: string;
  summary: AnalyticsSummary;
  timeseries: TimeseriesPoint[];
  models: ModelUsage[];
};

export const analyticsApi = {
  get: (
    orgId: string,
    token: string,
    params: { range: string; projectId?: string; start?: string; end?: string },
  ) => {
    const search = new URLSearchParams({ range: params.range });
    if (params.projectId) search.set("project_id", params.projectId);
    if (params.start) search.set("start", params.start);
    if (params.end) search.set("end", params.end);
    return apiFetch<AnalyticsResponse>(
      `/organizations/${orgId}/analytics?${search.toString()}`,
      {},
      token,
    );
  },
};

export type EvaluatorTypeInfo = {
  type: string;
  title: string;
  description: string;
  requires_expected_output: boolean;
  default_threshold: number;
  default_config: Record<string, unknown>;
};

export type Dataset = {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  item_count: number;
  created_at: string;
  updated_at: string;
};

export type DatasetItem = {
  id: string;
  dataset_id: string;
  name: string | null;
  input: unknown;
  expected_output: unknown;
  metadata: unknown;
  created_at: string;
};

export type Evaluator = {
  id: string;
  project_id: string;
  name: string;
  evaluator_type: string;
  description: string | null;
  config: Record<string, unknown> | null;
  threshold: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type EvaluatorScore = {
  evaluator_id: string | null;
  evaluator_name: string;
  evaluator_type: string;
  count: number;
  passed: number;
  failed: number;
  pass_rate: number;
  avg_score: number;
};

export type FailureCategory = { label: string; count: number };

export type EvaluationResult = {
  id: string;
  run_id: string;
  evaluator_id: string | null;
  evaluator_name: string;
  evaluator_type: string;
  dataset_item_id: string | null;
  trace_id: string | null;
  subject_key: string;
  score: number;
  passed: boolean;
  label: string | null;
  reasoning: string | null;
  output: unknown;
  expected_output: unknown;
  latency_ms: number | null;
  cost: string | number;
  created_at: string;
};

export type EvaluationRun = {
  id: string;
  project_id: string;
  dataset_id: string | null;
  dataset_name: string | null;
  name: string;
  target: string;
  status: string;
  agent_version: string | null;
  prompt_version: string | null;
  model_version: string | null;
  total_items: number;
  passed_count: number;
  failed_count: number;
  pass_rate: number;
  avg_score: number | null;
  total_cost: string | number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type EvaluationRunDetail = EvaluationRun & {
  evaluator_scores: EvaluatorScore[];
  failure_categories: FailureCategory[];
  skipped_evaluators: string[];
  results: EvaluationResult[];
};

export type MetricDelta = {
  metric: string;
  baseline: number | null;
  candidate: number | null;
  delta: number | null;
  pct_change: number | null;
  higher_is_better: boolean;
  regression: boolean;
};

export type EvaluatorDelta = {
  evaluator_name: string;
  evaluator_type: string;
  baseline_pass_rate: number | null;
  candidate_pass_rate: number | null;
  baseline_avg_score: number | null;
  candidate_avg_score: number | null;
  pass_rate_delta: number | null;
  regression: boolean;
};

export type SubjectChange = {
  subject_key: string;
  subject_name: string | null;
  evaluator_name: string;
  baseline_score: number;
  candidate_score: number;
  label: string | null;
  reasoning: string | null;
  dataset_item_id: string | null;
  trace_id: string | null;
};

export type Verdict = "pass" | "warn" | "fail";

export type RunComparison = {
  baseline: EvaluationRun;
  candidate: EvaluationRun;
  metrics: MetricDelta[];
  evaluator_deltas: EvaluatorDelta[];
  newly_failing: SubjectChange[];
  newly_passing: SubjectChange[];
  verdict: Verdict;
  summary: string;
};

export type TraceSelector = {
  agent_name?: string;
  status?: string;
  agent_version?: string;
  prompt_version?: string;
  limit?: number;
};

export type EvaluationRunInput = {
  name: string;
  target: "dataset" | "traces";
  dataset_id?: string;
  evaluator_ids?: string[];
  selector?: TraceSelector;
  agent_version?: string;
  outputs?: {
    dataset_item_id?: string;
    item_name?: string;
    output?: unknown;
    status?: string;
    duration_ms?: number;
  }[];
};

export const evaluationsApi = {
  listEvaluatorTypes: (token: string) =>
    apiFetch<EvaluatorTypeInfo[]>("/evaluator-types", {}, token),

  listDatasets: (projectId: string, token: string) =>
    apiFetch<Dataset[]>(`/projects/${projectId}/datasets`, {}, token),

  createDataset: (
    projectId: string,
    data: { name: string; description?: string },
    token: string,
  ) =>
    apiFetch<Dataset>(
      `/projects/${projectId}/datasets`,
      { method: "POST", body: JSON.stringify(data) },
      token,
    ),

  deleteDataset: (datasetId: string, token: string) =>
    apiFetch<void>(`/datasets/${datasetId}`, { method: "DELETE" }, token),

  listDatasetItems: (datasetId: string, token: string) =>
    apiFetch<DatasetItem[]>(`/datasets/${datasetId}/items`, {}, token),

  addDatasetItems: (
    datasetId: string,
    items: { name?: string; input?: unknown; expected_output?: unknown }[],
    token: string,
    replace = false,
  ) =>
    apiFetch<DatasetItem[]>(
      `/datasets/${datasetId}/items`,
      { method: "POST", body: JSON.stringify({ items, replace }) },
      token,
    ),

  listEvaluators: (projectId: string, token: string) =>
    apiFetch<Evaluator[]>(`/projects/${projectId}/evaluators`, {}, token),

  createEvaluator: (
    projectId: string,
    data: {
      name: string;
      evaluator_type: string;
      description?: string;
      config?: Record<string, unknown>;
      threshold?: number;
    },
    token: string,
  ) =>
    apiFetch<Evaluator>(
      `/projects/${projectId}/evaluators`,
      { method: "POST", body: JSON.stringify(data) },
      token,
    ),

  updateEvaluator: (
    evaluatorId: string,
    data: { is_active?: boolean; threshold?: number },
    token: string,
  ) =>
    apiFetch<Evaluator>(
      `/evaluators/${evaluatorId}`,
      { method: "PATCH", body: JSON.stringify(data) },
      token,
    ),

  deleteEvaluator: (evaluatorId: string, token: string) =>
    apiFetch<void>(`/evaluators/${evaluatorId}`, { method: "DELETE" }, token),

  listRuns: (projectId: string, token: string) =>
    apiFetch<{ items: EvaluationRun[]; total: number }>(
      `/projects/${projectId}/evaluation-runs`,
      {},
      token,
    ),

  createRun: (projectId: string, data: EvaluationRunInput, token: string) =>
    apiFetch<EvaluationRunDetail>(
      `/projects/${projectId}/evaluation-runs`,
      { method: "POST", body: JSON.stringify(data) },
      token,
    ),

  getRun: (runId: string, token: string) =>
    apiFetch<EvaluationRunDetail>(`/evaluation-runs/${runId}`, {}, token),

  compareRuns: (runId: string, baselineId: string, token: string) =>
    apiFetch<RunComparison>(
      `/evaluation-runs/${runId}/compare?baseline=${baselineId}`,
      {},
      token,
    ),
};

export type VersionStats = {
  version: string;
  runs: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  error_rate: number;
  avg_latency_ms: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_tokens: number;
  avg_tokens: number | null;
  total_cost: string | number;
  avg_cost: string | number;
  first_seen: string | null;
  last_seen: string | null;
};

export type VersionListResponse = {
  dimension: string;
  range: string;
  start: string;
  end: string;
  versions: VersionStats[];
};

export type VersionComparison = {
  dimension: string;
  range: string;
  start: string;
  end: string;
  baseline: VersionStats;
  candidate: VersionStats;
  metrics: MetricDelta[];
  verdict: Verdict;
  summary: string;
};

export const versionsApi = {
  list: (projectId: string, token: string, params: { dimension: string; range: string }) => {
    const search = new URLSearchParams(params);
    return apiFetch<VersionListResponse>(
      `/projects/${projectId}/versions?${search.toString()}`,
      {},
      token,
    );
  },

  compare: (
    projectId: string,
    token: string,
    params: { dimension: string; range: string; baseline: string; candidate: string },
  ) => {
    const search = new URLSearchParams(params);
    return apiFetch<VersionComparison>(
      `/projects/${projectId}/versions/compare?${search.toString()}`,
      {},
      token,
    );
  },
};

export type SystemInfo = {
  name: string;
  version: string;
  environment: string;
  database_backend: string;
  token_store: string;
  judge_configured: boolean;
  judge_model: string;
  uptime_seconds: number;
  rate_limit_enabled: boolean;
  rate_limit_requests: number;
  rate_limit_window_seconds: number;
};

export type SystemMetrics = {
  uptime_seconds: number;
  requests: number;
  client_errors: number;
  server_errors: number;
  error_rate: number;
  p50_ms: number | null;
  p95_ms: number | null;
  streams: {
    subscribers: number;
    projects_watched: number;
    events_published: number;
    events_dropped: number;
  };
  routes: {
    route: string;
    requests: number;
    client_errors: number;
    server_errors: number;
    avg_ms: number | null;
    p50_ms: number | null;
    p95_ms: number | null;
    max_ms: number;
  }[];
};

export type UsageResponse = {
  organization_id: string;
  projects: number;
  traces: number;
  spans: number;
  llm_calls: number;
  tool_calls: number;
  events: number;
  datasets: number;
  dataset_items: number;
  evaluators: number;
  evaluation_runs: number;
  traces_last_24h: number;
  tokens_last_24h: number;
  cost_last_24h: string | number;
  oldest_trace_at: string | null;
  newest_trace_at: string | null;
};

export const systemApi = {
  info: (token: string) => apiFetch<SystemInfo>("/system/info", {}, token),
  metrics: (token: string) => apiFetch<SystemMetrics>("/system/metrics", {}, token),
  usage: (orgId: string, token: string) =>
    apiFetch<UsageResponse>(`/organizations/${orgId}/usage`, {}, token),
};

export function streamUrl(projectId: string, token: string): string {
  return `${API_URL}${API_PREFIX}/projects/${projectId}/stream?token=${encodeURIComponent(token)}`;
}
