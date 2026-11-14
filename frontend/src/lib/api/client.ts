import { ErrorCode, Problem } from "./types";

export class ApiError extends Error {
  code: ErrorCode;
  status: number;
  detail: string;
  requestId?: string;

  constructor(problem: Problem) {
    super(problem.detail || problem.title || "API Error");
    this.name = "ApiError";
    this.code = problem.code;
    this.status = problem.status;
    this.detail = problem.detail;
    this.requestId = problem.request_id;
  }
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function apiClient<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = path.startsWith("http")
    ? path
    : `${BASE_URL.replace(/\/$/, "")}/api/v1${path.startsWith("/") ? path : `/${path}`}`;

  const headers = new Headers(options.headers || {});
  const method = (options.method || "GET").toUpperCase();

  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-RAG-Client", "web");
  }

  if (
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type") &&
    options.body
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let problem: Problem;
    try {
      const json = await response.json();
      problem = {
        type: json.type || "https://rag.local/errors/internal",
        title: json.title || response.statusText,
        status: json.status || response.status,
        code: (json.code || "internal") as ErrorCode,
        detail: json.detail || "An unexpected error occurred",
        request_id: json.request_id,
      };
    } catch {
      problem = {
        type: "https://rag.local/errors/internal",
        title: response.statusText,
        status: response.status,
        code: "internal",
        detail: `HTTP error ${response.status}: ${response.statusText}`,
      };
    }
    throw new ApiError(problem);
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }

  return (await response.text()) as unknown as T;
}
