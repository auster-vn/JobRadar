import {NextRequest, NextResponse} from "next/server";

export function proxy(request: NextRequest) {
  const secret = process.env.PROXY_SHARED_SECRET;
  if (!secret) return NextResponse.next();

  const backend = process.env.API_INTERNAL_URL;
  if (process.env.VERCEL !== "1" || secret.length < 32 || !backend) {
    return new NextResponse("Proxy configuration unavailable", {status: 503});
  }
  const target = new URL(backend);
  if (target.protocol !== "https:" || target.username || target.password) {
    return new NextResponse("Proxy configuration unavailable", {status: 503});
  }
  // Assign the path, rather than resolving a user-controlled //host against the URL.
  target.pathname = request.nextUrl.pathname;
  target.search = request.nextUrl.search;
  const headers = new Headers(request.headers);
  // Vercel overwrites this header at ingress. Never accept the caller's custom headers.
  const clientIp = request.headers.get("x-vercel-forwarded-for")?.trim();
  if (!clientIp) return new NextResponse("Client address unavailable", {status: 503});
  headers.set("x-jobradar-client-ip", clientIp);
  headers.set("x-jobradar-proxy-secret", secret);
  return NextResponse.rewrite(target, {request: {headers}});
}

export const config = {
  matcher: ["/api/:path*", "/health/:path*", "/version"],
};
