import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "https://planforge.in";
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/dashboard", "/projects/", "/account", "/team", "/api/"],
      },
    ],
    sitemap: `${base}/sitemap.xml`,
  };
}
