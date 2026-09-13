const API = (import.meta.env?.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function apiAssetUrl(path: string): string {
  return /^https?:\/\//i.test(path) ? path : `${API}/${path.replace(/^\/+/, "")}`;
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const timeout = AbortSignal.timeout(15000);
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
    signal: options?.signal ? AbortSignal.any([options.signal, timeout]) : timeout,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 404 && !path.startsWith("/runs/")) {
      throw new ApiError(response.status,
        "The PersonaAgent API was not found. Start the FastAPI backend on port 8000, then try again.",
      );
    }
    throw new ApiError(response.status,
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed (${response.status}). Check that the backend is running.`,
    );
  }
  return response.json();
}
