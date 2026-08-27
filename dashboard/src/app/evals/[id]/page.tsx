import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { StatusPill } from "@/components/StatusPill";
import { AnimatedNumber } from "@/components/AnimatedNumber";

export default async function EvalDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { userId, getToken } = await auth();
  if (!userId) redirect("/sign-in");
  const token = (await getToken()) ?? "";
  const evaluation = await api.getEvaluation(token, id);

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-medium tracking-tight">{evaluation.prompt_version}</h1>
          <p className="text-sm text-bone-dim">
            {evaluation.commit_hash?.slice(0, 7)} &middot; {evaluation.model_name}
          </p>
        </div>
        <StatusPill status={evaluation.status} />
      </div>

      <div className="overflow-hidden rounded border border-ink-raised">
        {evaluation.results.map((result, i) => (
          <div
            key={result.id}
            className="flex items-center justify-between border-b border-ink-raised px-4 py-3 text-sm last:border-b-0"
            style={{ animationDelay: `${i * 30}ms` }}
          >
            <span className="capitalize">{result.metric_name}</span>
            <div className="flex items-center gap-3">
              <span className="tabular-nums text-bone-dim">
                <AnimatedNumber value={result.metric_value ?? 0} decimals={2} />
              </span>
              <StatusPill status={result.status} />
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}