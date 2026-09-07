import { cn } from "@/lib/utils";

/** Placeholder block that reserves layout while content loads. */
function Skeleton({ className, ...props }) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-none border border-white/5 bg-white/5", className)}
      {...props}
    />
  );
}

/** Full-panel loading state, used as the fallback for lazily loaded tabs. */
function PanelSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-48" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <Skeleton className="h-64" />
      <span className="sr-only">Loading</span>
    </div>
  );
}

export { Skeleton, PanelSkeleton };
