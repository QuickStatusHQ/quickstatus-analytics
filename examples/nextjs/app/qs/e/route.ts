// Forwards analytics beacons to QuickStatus.dev with the visitor's IP. Cookies are not forwarded.
export const runtime = "edge";

export async function POST(request: Request) {
  // On Vercel the first X-Forwarded-For entry is the visitor (Vercel sets the header). Self-hosted
  // behind your own proxy, the client can write that entry: use the address your proxy appended
  // (usually the last entry) instead.
  const forwarded = request.headers.get("x-forwarded-for") || "";
  const ip = forwarded.split(",")[0]?.trim() || request.headers.get("x-real-ip") || "";
  const response = await fetch("https://a.quickstatus.dev/e", {
    method: "POST",
    body: await request.text(),
    headers: {
      "Content-Type": "text/plain",
      "User-Agent": request.headers.get("user-agent") || "",
      "X-Forwarded-For": ip,
      "X-QS-Proxy": "1",
    },
  });
  return new Response(null, { status: response.status });
}
