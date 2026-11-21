/** @type {import('next').NextConfig} */
module.exports = {
  async rewrites() {
    return [{ source: "/qs.js", destination: "https://quickstatus.dev/qs.js" }];
  },
};
