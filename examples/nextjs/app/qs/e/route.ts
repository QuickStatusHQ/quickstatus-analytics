// Forwards analytics beacons to QuickStatus.dev with the visitor's IP.
export const runtime = "edge";

export async function POST(request: Request) {
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
