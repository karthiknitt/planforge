import type { Metadata } from "next";
import { JetBrains_Mono, Outfit, Plus_Jakarta_Sans } from "next/font/google";
import { ThemeProvider } from "@/components/theme-provider";
import { LocaleProvider } from "@/lib/locale-context";
import "./globals.css";

const displayFont = Outfit({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800", "900"],
});

const bodyFont = Plus_Jakarta_Sans({
  variable: "--font-body",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const monoFont = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://planforge.in"),
  title: {
    default: "PlanForge — G+1 Floor Plan Generator for Indian Builders",
    template: "%s | PlanForge",
  },
  description:
    "Generate NBC 2016-compliant G+1 residential floor plans instantly. Enter plot dimensions, get 5 layout variations, export PDF & DXF. Built for Indian civil engineers and small builders.",
  keywords: [
    "floor plan generator India",
    "G+1 floor plan",
    "NBC 2016 compliant floor plan",
    "house plan generator",
    "residential floor plan India",
    "2BHK floor plan",
    "3BHK floor plan",
    "Indian house design",
    "plot plan Bangalore",
    "civil engineer software India",
    "DXF floor plan",
    "BOQ calculator India",
  ],
  authors: [{ name: "PlanForge" }],
  creator: "PlanForge",
  publisher: "PlanForge",
  category: "Architecture & Design Software",
  openGraph: {
    type: "website",
    siteName: "PlanForge",
    locale: "en_IN",
    images: [
      {
        url: "/opengraph-image.png",
        width: 1424,
        height: 752,
        alt: "PlanForge — G+1 Floor Plan Generator for Indian Builders",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    creator: "@planforge_in",
    images: ["/opengraph-image.png"],
  },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icon.png", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  robots: { index: true, follow: true, googleBot: { index: true, follow: true } },
  alternates: { canonical: "/" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en-IN" suppressHydrationWarning>
      <body
        className={`${displayFont.variable} ${bodyFont.variable} ${monoFont.variable} antialiased`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <LocaleProvider>{children}</LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
