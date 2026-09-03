"use client";

import { useActionState } from "react";
import { createProjectAction, type CreateProjectState } from "@/app/actions";

const initialState: CreateProjectState = { error: null };

export function AddProjectForm() {
  const [state, formAction, pending] = useActionState(createProjectAction, initialState);

  return (
    <form action={formAction} className="mb-6 rounded border border-ink-raised p-4">
      <h2 className="mb-3 text-sm uppercase tracking-wide text-bone-dim">Add a project</h2>

      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          name="name"
          placeholder="Project name"
          required
          className="flex-1 rounded border border-ink-raised bg-ink px-3 py-2 text-sm outline-none transition-colors duration-150 focus:border-acid"
        />
        <input
          name="github_repo_url"
          placeholder="owner/repo or https://github.com/owner/repo"
          required
          className="flex-[2] rounded border border-ink-raised bg-ink px-3 py-2 text-sm outline-none transition-colors duration-150 focus:border-acid"
        />
        <button
          type="submit"
          disabled={pending}
          className="rounded bg-acid px-4 py-2 text-sm font-medium text-ink transition-opacity duration-150 hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Adding..." : "Add"}
        </button>
      </div>

      {state.error ? <p className="mt-3 text-sm text-fail">{state.error}</p> : null}

      <p className="mt-3 text-xs text-bone-dim">
        Install the AutoEvalOps GitHub App on this repository, then add{" "}
        <code className="text-bone">prompts/*.txt</code> and matching{" "}
        <code className="text-bone">eval/*.test_cases.json</code> files. Evaluations run
        automatically on every pull request that touches a prompt.
      </p>
    </form>
  );
}