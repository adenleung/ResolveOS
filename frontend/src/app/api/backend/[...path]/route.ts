import { NextRequest, NextResponse } from "next/server";
import { allowed, sameOrigin } from "@/lib/proxy-policy";
import { backend, COOKIE, frontendOrigin } from "@/lib/server-backend";
export const dynamic = "force-dynamic";
async function forward(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const path = (await context.params).path.join("/");
  if (!allowed(path, request.method)) return NextResponse.json({detail: "Endpoint unavailable in the employee workbench"}, {status: 404});
  if (request.method !== "GET" && !sameOrigin(request.headers.get("origin"), frontendOrigin())) return NextResponse.json({detail: "Cross-origin mutation denied"}, {status: 403});
  const token = request.cookies.get(COOKIE)?.value;
  if (!token) return NextResponse.json({detail: "Session required. Reconnect with an authorized token."}, {status: 401});
  const body = request.method === "GET" ? undefined : await request.text();
  if (body && Buffer.byteLength(body) > 65536) return NextResponse.json({detail: "Request too large"}, {status: 413});
  try {
    const response = await fetch(`${backend()}/api/v1/${path}${request.nextUrl.search}`, { method: request.method, body,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, cache: "no-store", signal: AbortSignal.timeout(15000) });
    if (!response.headers.get("content-type")?.includes("application/json")) return NextResponse.json({detail: "Backend request failed; no result was established."}, {status: 502});
    return NextResponse.json(await response.json(), {status: response.status, headers: {"Cache-Control": "no-store"}});
  } catch { return NextResponse.json({detail: "Backend unavailable. No action result was established; refresh before retrying."}, {status: 502}); }
}
export const GET = forward;
export const POST = forward;
