import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Button } from "@/components/ui/button";
import { auth } from "@/lib/auth";

export const metadata: Metadata = { title: "Dashboard" };

interface Project {
  id: string;
  name: string;
  plot_length: number;
  plot_width: number;
  num_bedrooms: number;
  toilets: number;
  parking: boolean;
  city: string | null;
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
            <div key={p.id} className="rounded-xl border bg-card p-5 flex flex-col gap-3">
              <div className="font-bold text-base">{p.name}</div>
              <div className="flex flex-wrap gap-1.5">
                <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium">
                  {p.plot_length} × {p.plot_width} m
                </span>
                <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium">
                  {p.num_bedrooms} BHK · {p.toilets}T{p.parking ? " · Parking" : ""}
                </span>
                {p.city && p.city !== "other" && (
                  <span className="inline-flex items-center rounded-md bg-[#1e3a5f]/8 text-[#1e3a5f] px-2 py-0.5 text-xs font-medium capitalize">
                    {p.city}
                  </span>
                )}
              </div>
              <div className="text-xs text-muted-foreground">
                {new Date(p.created_at).toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </div>
              <div className="mt-auto flex gap-2 pt-1">
                <Button size="sm" asChild>
                  <Link href={`/projects/${p.id}`}>View →</Link>
                </Button>
                <Button variant="ghost" size="sm" asChild>
                  <Link href={`/projects/${p.id}/edit`}>Edit</Link>
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
