export interface Project {
  id: string;
  org_id: string;
  name: string;
  github_repo_url: string | null;
  created_at: string;
}

export interface EvaluationSummary {
  id: string;
  project_id: string;
  commit_hash: string | null;
  prompt_version: string | null;
  model_name: string | null;
  test_cases_count: number;
  status: string;
  created_at: string;
  completed_at: string | null;
}

export interface EvalResultRow {
  id: string;
  metric_name: string | null;
  metric_value: number | null;
  status: string;
}

export interface EvaluationDetail extends EvaluationSummary {
  results_json: Record<string, unknown> | null;
  results: EvalResultRow[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, token: string): Promise<T> {
  console.log("DEBUG token:", token ? `${token.slice(0, 20)}... (length ${token.length})` : "EMPTY/UNDEFINED");
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} on ${path}`);
  }
  return res.json();
}

export const api = {
  listProjects: (token: string) => request<Project[]>("/api/v1/projects", token),
  listEvaluations: (token: string, projectId: string) =>
    request<EvaluationSummary[]>(`/api/v1/projects/${projectId}/evals`, token),
  getEvaluation: (token: string, evalId: string) =>
    request<EvaluationDetail>(`/api/v1/evals/${evalId}`, token),
};

export { ApiError };