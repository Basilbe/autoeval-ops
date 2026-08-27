import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { StatusPill } from "@/components/StatusPill";

export default async function EvalHistoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { userId, getToken } = await auth();
  if (!userId) redirect("/sign-in");
  const token = (await getToken()) ?? "";
  const evaluations = await api.listEvaluations(token, id);

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <Link href="/" className="text-sm text-bone-dim transition-colors duration-150 hover:text-bone">
        &larr; Projects
      </Link>
      <h1 className="mb-6 mt-2 text-lg font-medium tracking-tight">Evaluation History</h1>

      {evaluations.length === 0 ? (
        <div className="rounded border border-ink-raised px-6 py-16 text-center text-bone-dim">
          No evaluations yet. They appear here once a PR triggers the webhook.
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-ink-raised">
          {evaluations.map((eval_, i) => (
            <Link
              key={eval_.id}
              href={`/evals/${eval_.id}`}
              className="flex items-center gap-4 border-b border-ink-raised px-4 py-3 text-sm transition-colors duration-150 last:border-b-0 hover:bg-ink-raised"
              style={{ animationDelay: `${i * 20}ms` }}
            >
              <span className="w-20 truncate text-bone-dim">
                {eval_.commit_hash?.slice(0, 7) ?? "-"}
              </span>
              <span className="flex-1 truncate">{eval_.prompt_version ?? "-"}</span>
              <span className="text-bone-dim">{eval_.test_cases_count} cases</span>
              <StatusPill status={eval_.status} />
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}