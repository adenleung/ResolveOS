export const COOKIE = "resolveos_session";
export function frontendOrigin(): string {
  const url = new URL(process.env.RESOLVEOS_FRONTEND_ORIGIN ?? "http://127.0.0.1:3000");
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/") throw new Error("Invalid frontend origin configuration");
  return url.origin;
}
export function backend(): string {
  const url = new URL(process.env.RESOLVEOS_BACKEND_URL ?? "http://127.0.0.1:8000");
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/") throw new Error("Invalid server backend configuration");
  return url.origin;
}
