import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { SignOutButton } from "./sign-out-button";

interface Project {
  id: string;
  name: string;
  plot_length: number;
  plot_width: number;
  bhk: number;
  toilets: number;
  parking: boolean;
  created_at: string;
}

async function fetchProjects(userId: string): Promise<Project[]> {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/projects`, {
      headers: { "X-User-Id": userId },
      cache: "no-store",
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function DashboardPage() {
  const session = await auth.api.getSession({ headers: await headers() });

  if (!session) {
    redirect("/sign-in");
  }

  const projects = await fetchProjects(session.user.id);

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
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Welcome, {session.user.name}</h1>
            <p className="mt-1 text-muted-foreground">Your floor plan projects</p>
          </div>
          <Button asChild>
            <Link href="/projects/new">+ New project</Link>
          </Button>
        </div>

        {projects.length === 0 ? (
          <div className="rounded-xl border border-dashed p-12 text-center text-muted-foreground">
            No projects yet.{" "}
            <Link href="/projects/new" className="text-foreground underline underline-offset-4">
              Create your first project
            </Link>{" "}
            to get started.
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <div key={p.id} className="rounded-xl border bg-card p-5 flex flex-col gap-2">
                <div className="font-semibold">{p.name}</div>
                <div className="text-sm text-muted-foreground">
                  {p.plot_length}m × {p.plot_width}m &middot; {p.bhk} BHK &middot; {p.toilets}T
                  {p.parking && " · Parking"}
                </div>
                <div className="mt-auto pt-3">
                  <Button variant="outline" size="sm" asChild>
                    <Link href={`/projects/${p.id}`}>View</Link>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
