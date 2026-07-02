"use server";

import { revalidatePath } from "next/cache";

export async function invalidateProjectLayouts(projectId: string): Promise<void> {
  revalidatePath(`/projects/${projectId}`);
}
