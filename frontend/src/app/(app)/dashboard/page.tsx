import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { SignOutButton } from "./sign-out-button";

export default async function DashboardPage() {
  const session = await auth.api.getSession({ headers: await headers() });

  if (!session) {
    redirect("/sign-in");
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <span className="font-semibold">PlanForge</span>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">{session.user.email}</span>
            <SignOutButton />
          </div>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-10">
        <div>
          <h1 className="text-2xl font-bold">Welcome, {session.user.name}</h1>
          <p className="mt-1 text-muted-foreground">
            Your projects will appear here. Start by creating a new floor plan.
          </p>
        </div>
        <div className="rounded-xl border border-dashed p-12 text-center text-muted-foreground">
          No projects yet — coming soon.
        </div>
      </main>
    </div>
  );
}
