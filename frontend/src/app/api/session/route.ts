import { NextRequest, NextResponse } from "next/server";
import { backend, COOKIE, frontendOrigin } from "@/lib/server-backend";
import { sameOrigin } from "@/lib/proxy-policy";
export const dynamic = "force-dynamic";
export async function GET(request: NextRequest) {
  const token = request.cookies.get(COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Connect with an authorized development token" }, { status: 401 });
  try {
    const response = await fetch(`${backend()}/api/v1/workbench/identity`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store", signal: AbortSignal.timeout(15000) });
    return NextResponse.json(await response.json(), { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch { return NextResponse.json({ detail: "Backend unavailable. Check the local backend and database." }, { status: 502 }); }
}
export async function POST(request: NextRequest) {
  if (!sameOrigin(request.headers.get("origin"), frontendOrigin())) return NextResponse.json({ detail: "Cross-origin session request denied" }, { status: 403 });
  let token: unknown;
  try { token = (await request.json()).token; } catch { return NextResponse.json({detail: "Invalid session request"}, {status: 400}); }
  if (typeof token !== "string" || token.length < 24 || token.length > 4096 || /[\r\n]/.test(token)) return NextResponse.json({ detail: "A valid authorized development token is required" }, { status: 400 });
  try {
    const response = await fetch(`${backend()}/api/v1/workbench/identity`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store", signal: AbortSignal.timeout(15000) });
    const body = await response.json();
    const result = NextResponse.json(body, { status: response.status, headers: { "Cache-Control": "no-store" } });
    if (response.ok) result.cookies.set(COOKIE, token, { httpOnly: true, secure: frontendOrigin().startsWith("https:"), sameSite: "strict", path: "/", maxAge: 3600 });
    return result;
  } catch { return NextResponse.json({detail: "Backend unavailable. Check the local backend and database."}, {status: 502}); }
}
export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request.headers.get("origin"), frontendOrigin())) return NextResponse.json({detail: "Cross-origin request denied"}, {status: 403});
  const result = NextResponse.json({ disconnected: true }); result.cookies.delete(COOKIE); return result;
}
