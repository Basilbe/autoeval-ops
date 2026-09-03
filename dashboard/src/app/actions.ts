"use server";

import { auth } from "@clerk/nextjs/server";
import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";

export type CreateProjectState = { error: string | null };

export async function createProjectAction(
  _prev: CreateProjectState,
  formData: FormData
): Promise<CreateProjectState> {
  const { userId, getToken } = await auth();
  if (!userId) return { error: "Not signed in." };

  const name = String(formData.get("name") ?? "").trim();
  const repoUrl = String(formData.get("github_repo_url") ?? "").trim();

  if (!name || !repoUrl) {
    return { error: "Both a project name and a repository URL are required." };
  }

  const token = (await getToken()) ?? "";

  try {
    // Every project needs an owning organization. Reuse the first one if
    // the user has any; otherwise create a default so first-time users
    // don't have to think about organizations at all.
    const orgs = await api.listOrganizations(token);
    const org = orgs.length > 0 ? orgs[0] : await api.createOrganization(token, "My Org");

    await api.createProject(token, org.id, { name, github_repo_url: repoUrl });
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Could not create project." };
  }

  revalidatePath("/");
  return { error: null };
}