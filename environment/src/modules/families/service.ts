import { prisma } from "../../lib/prisma";

export async function listFamiliesForUser(userId: string) {
  const memberships = await prisma.familyMember.findMany({
    where: { userId },
    include: { family: true },
    orderBy: { createdAt: "asc" }
  });

  return memberships.map((membership) => ({
    id: membership.family.id,
    slug: membership.family.slug,
    name: membership.family.name,
    timezone: membership.family.timezone,
    locationSharingEnabled: membership.family.locationSharingEnabled,
    role: membership.role,
    permissions: membership.permissions
  }));
}

export async function getFamilySummary(familyId: string, userId: string) {
  const membership = await prisma.familyMember.findUnique({
    where: {
      familyId_userId: {
        familyId,
        userId
      }
    },
    include: { family: true }
  });

  if (!membership) {
    return null;
  }

  const [taskCount, eventCount, reminderCount, listCount, postCount] = await Promise.all([
    prisma.householdTask.count({ where: { familyId } }),
    prisma.calendarEvent.count({ where: { familyId } }),
    prisma.reminder.count({ where: { familyId } }),
    prisma.familyList.count({ where: { familyId } }),
    prisma.familyPost.count({ where: { familyId } })
  ]);

  return {
    id: membership.family.id,
    slug: membership.family.slug,
    name: membership.family.name,
    timezone: membership.family.timezone,
    locationSharingEnabled: membership.family.locationSharingEnabled,
    membershipRole: membership.role,
    counts: {
      tasks: taskCount,
      events: eventCount,
      reminders: reminderCount,
      lists: listCount,
      posts: postCount
    }
  };
}

export async function listFamilyLists(familyId: string) {
  const lists = await prisma.familyList.findMany({
    where: { familyId },
    include: {
      items: {
        orderBy: { createdAt: "asc" }
      }
    },
    orderBy: { createdAt: "asc" }
  });

  return lists.map((list) => ({
    id: list.id,
    title: list.title,
    visibility: list.visibility,
    items: list.items.map((item) => ({
      id: item.id,
      label: item.label,
      completed: item.completed
    }))
  }));
}

export async function listFamilyReminders(familyId: string) {
  const reminders = await prisma.reminder.findMany({
    where: { familyId },
    include: { recipient: true },
    orderBy: { createdAt: "asc" }
  });

  return reminders.map((reminder) => ({
    id: reminder.id,
    title: reminder.title,
    scheduleText: reminder.scheduleText,
    recipient: reminder.recipient
      ? {
          id: reminder.recipient.id,
          displayName: reminder.recipient.displayName
        }
      : null
  }));
}
