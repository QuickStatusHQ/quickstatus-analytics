// Serves the tracker from your own domain. A route handler, not a rewrite: a rewrite to another
// host forwards the visitor's request headers, cookies included.
export const runtime = "edge";

export async function GET() {
  const response = await fetch("https://quickstatus.dev/qs.js", { next: { revalidate: 300 } });
  // Only the script itself is cached and served as JavaScript, never an error page.
  if (!response.ok) return new Response(null, { status: 502, headers: { "Cache-Control": "no-store" } });
  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=300",
    },
  });
}
