export default function ProjectLoading() {
  return (
    <div className="flex min-h-screen flex-col">
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-10">
        {/* Summary strip skeleton */}
        <div className="flex flex-wrap gap-6 rounded-xl border bg-muted/40 px-5 py-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="flex flex-col gap-1.5">
              <div className="h-3 w-20 animate-pulse rounded bg-muted" />
              <div className="h-5 w-28 animate-pulse rounded bg-muted" />
            </div>
          ))}
        </div>
        {/* Layout selector skeleton */}
        <div className="flex gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-9 w-24 animate-pulse rounded-md bg-muted" />
          ))}
        </div>
        {/* SVG area skeleton */}
        <div className="rounded-xl border bg-muted/20 h-96 animate-pulse" />
      </div>
    </div>
  );
}
