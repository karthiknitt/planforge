"use client";

import { useRouter } from "next/navigation";
import Script from "next/script";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/auth-client";

interface PricingCheckoutButtonProps {
  plan: "basic" | "pro";
  label: string;
  highlight?: boolean;
}

export function PricingCheckoutButton({ plan, label, highlight }: PricingCheckoutButtonProps) {
  const { data: session } = useSession();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleCheckout() {
    if (!session) {
      router.push("/sign-in?redirect=/pricing");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const orderRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/payments/order`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": session.user.id,
        },
        body: JSON.stringify({ plan }),
      });

      if (!orderRes.ok) {
        const data = await orderRes.json().catch(() => ({}));
        throw new Error(data?.detail ?? "Failed to create payment order");
      }

      const { order_id, amount, key_id } = await orderRes.json();

      const rzp = new (
        window as unknown as { Razorpay: new (opts: unknown) => { open: () => void } }
      ).Razorpay({
        key: key_id,
        order_id,
        amount,
        currency: "INR",
        name: "PlanForge",
        description: `${plan === "basic" ? "Basic" : "Pro"} Plan — 30 days`,
        prefill: {
          name: session.user.name,
          email: session.user.email,
        },
        handler: async (response: { razorpay_payment_id: string; razorpay_signature: string }) => {
          await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/payments/verify`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-User-Id": session.user.id,
            },
            body: JSON.stringify({
              order_id,
              payment_id: response.razorpay_payment_id,
              signature: response.razorpay_signature,
              plan,
            }),
          });
          router.push("/dashboard?upgraded=1");
        },
        modal: {
          ondismiss: () => setLoading(false),
        },
      });

      rzp.open();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />
      <Button
        className={`w-full font-bold ${
          highlight
            ? "bg-[#f97316] hover:bg-[#ea6c0a] text-white"
            : "bg-[#1e3a5f] hover:bg-[#162d4a] text-white"
        }`}
        onClick={handleCheckout}
        disabled={loading}
      >
        {loading ? "Loading…" : label}
      </Button>
      {error && <p className="text-xs text-red-600 text-center">{error}</p>}
    </div>
  );
}
