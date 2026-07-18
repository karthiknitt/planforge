import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function ShareNotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <h2 className="font-semibold text-xl">Shared plan not found</h2>
      <p className="text-muted-foreground text-sm">This share link is invalid or has expired.</p>
      <Button asChild>
        <Link href="/">Back home</Link>
      </Button>
    </div>
  );
}
