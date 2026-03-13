import { prisma } from "../../lib/prisma";

export async function listTasksForFamily(familyId: string) {
  const tasks = await prisma.householdTask.findMany({
    where: { familyId },
    include: {
      assignee: true,
      createdBy: true
    },
    orderBy: { createdAt: "asc" }
  });

  return tasks.map((task) => ({
    id: task.id,
    familyId: task.familyId,
    title: task.title,
    description: task.description,
    cadence: task.cadence,
    status: task.status,
    visibility: task.visibility,
    dueAt: task.dueAt,
    createdBy: {
      id: task.createdBy.id,
      displayName: task.createdBy.displayName
    },
    assignee: task.assignee
      ? {
          id: task.assignee.id,
          displayName: task.assignee.displayName
        }
      : null
  }));
}
