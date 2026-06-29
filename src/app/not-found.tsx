import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-[100dvh] flex flex-col items-center justify-center text-center px-6 bg-background">
      <div className="w-16 h-16 rounded-lg bg-primary/10 flex items-center justify-center mb-8">
        <span className="text-primary font-bold text-2xl">T</span>
      </div>
      <h1 className="text-6xl font-semibold tracking-tight text-foreground leading-tight">
        404
      </h1>
      <p className="text-lg text-muted-foreground mt-4 max-w-md">
        This page doesn't exist. It may have been moved or the link is incorrect.
      </p>
      <Link
        href="/dashboard"
        className="mt-8 inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
      >
        Back to Dashboard
      </Link>
    </div>
  );
}
