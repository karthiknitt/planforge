import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "https://planforge.in";
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/how-it-works", "/pricing", "/sign-in", "/sign-up"],
        disallow: ["/dashboard", "/projects/"],
      },
    ],
    sitemap: `${base}/sitemap.xml`,
  };
}
