import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { UserButton } from "@clerk/nextjs";
import { api } from "@/lib/api";

export default async function ProjectsPage() {
  const { userId, getToken } = await auth();
  if (!userId) redirect("/sign-in");
  const token = (await getToken()) ?? "";
  const projects = await api.listProjects(token);

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-lg font-medium tracking-tight">AutoEvalOps</h1>
        <UserButton />
      </div>

      {projects.length === 0 ? (
        <div className="rounded border border-ink-raised px-6 py-16 text-center text-bone-dim">
          No projects registered yet. Register one via the API to see it here.
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-ink-raised">
          {projects.map((project, i) => (
            <Link
              key={project.id}
              href={`/projects/${project.id}`}
              className="flex items-center justify-between border-b border-ink-raised px-4 py-3 transition-colors duration-150 last:border-b-0 hover:bg-ink-raised"
              style={{ animationDelay: `${i * 20}ms` }}
            >
              <span className="font-medium">{project.name}</span>
              <span className="text-sm text-bone-dim">{project.github_repo_url}</span>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}