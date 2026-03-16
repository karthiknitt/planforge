"use server";

import { revalidateTag } from "next/cache";

export async function invalidateProjectLayouts(projectId: string): Promise<void> {
  revalidateTag(`project-${projectId}`);
}
