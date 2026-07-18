import { Skeleton } from "@/components/ui/skeleton";

export default function AccountLoading() {
  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col gap-6 px-4 py-12">
      <div className="mb-2 flex items-center gap-4">
        <Skeleton className="h-14 w-14 rounded-2xl" />
        <div className="space-y-2">
          <Skeleton className="h-7 w-28" />
          <Skeleton className="h-4 w-48" />
        </div>
      </div>
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ))}
    </main>
  );
}
