// Route your-site.com/qs.js and your-site.com/qs/e to this Worker.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/qs.js") {
      return fetch("https://quickstatus.dev/qs.js", { cf: { cacheTtl: 300 } });
    }
    if (url.pathname === "/qs/e" && request.method === "POST") {
      const ip = request.headers.get("CF-Connecting-IP") || "";
      return fetch("https://a.quickstatus.dev/e", {
        method: "POST",
        body: await request.text(),
        headers: {
          "Content-Type": "text/plain",
          "User-Agent": request.headers.get("User-Agent") || "",
          "X-Forwarded-For": ip,
          "X-QS-Proxy": "1",
        },
      });
    }
    return new Response("Not found", { status: 404 });
  },
};
