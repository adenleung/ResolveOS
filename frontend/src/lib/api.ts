export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { ...options, cache: "no-store", credentials: "same-origin", headers: { "Content-Type": "application/json", ...options?.headers } });
  const body: unknown = await response.json();
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? (body as {detail: unknown}).detail : "Request failed";
    throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body as T;
}
export function post<T>(path: string, body?: unknown): Promise<T> { return api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }); }
