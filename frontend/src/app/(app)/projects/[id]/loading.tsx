export default function ProjectLoading() {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-6">
      {/* Breadcrumb skeleton */}
      <div className="flex items-center gap-2">
        <div className="h-8 w-28 animate-pulse rounded-md bg-muted" />
        <div className="h-4 w-4 animate-pulse rounded bg-muted" />
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
      </div>
      {/* Summary strip skeleton */}
      <div className="flex flex-wrap gap-6 rounded-xl border bg-muted/40 px-5 py-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex flex-col gap-1.5">
            <div className="h-3 w-20 animate-pulse rounded bg-muted" />
            <div className="h-5 w-28 animate-pulse rounded bg-muted" />
          </div>
        ))}
      </div>
    </div>
  );
}
