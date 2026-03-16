import type { Metadata } from "next";
import { FadeIn } from "@/components/motion/fade-in";

export const metadata: Metadata = {
  title: "Privacy Policy | PlanForge",
  description: "PlanForge privacy policy — how we collect, use, and protect your data.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <div className="bg-background py-16 lg:py-24">
      <FadeIn className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
        <h1
          className="text-3xl md:text-4xl font-black text-foreground mb-2"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Privacy Policy
        </h1>
        <p className="text-sm text-muted-foreground mb-10">Last updated: March 2026</p>

        <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none space-y-8 text-foreground/80">
          <section>
            <h2 className="text-lg font-bold text-foreground mb-2">What we collect</h2>
            <p>
              When you create an account, we collect your email address and a hashed password. When
              you create a project, we store your plot configuration and the generated floor plan
              data. We do not collect payment card details — payments are processed by Razorpay.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-foreground mb-2">How we use your data</h2>
            <p>
              Your data is used solely to provide the PlanForge service: generating floor plans,
              storing your projects, and sending transactional emails (account verification,
              subscription receipts). We do not sell your data to third parties.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-foreground mb-2">Cookies</h2>
            <p>
              We use a single session cookie to keep you logged in. We do not use advertising
              cookies or third-party tracking cookies.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-foreground mb-2">Data retention</h2>
            <p>
              Your account and project data are retained as long as your account is active. You may
              delete your account at any time from account settings, which permanently removes all
              associated data within 30 days.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-foreground mb-2">Security</h2>
            <p>
              All data is transmitted over HTTPS. Passwords are hashed using bcrypt. We use
              PostgreSQL hosted in India with regular automated backups.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-foreground mb-2">Contact</h2>
            <p>
              For privacy enquiries, email{" "}
              <a href="mailto:privacy@planforge.in" className="text-primary hover:underline">
                privacy@planforge.in
              </a>
              .
            </p>
          </section>
        </div>
      </FadeIn>
    </div>
  );
}
