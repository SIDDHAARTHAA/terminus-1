import { prisma } from "../../lib/prisma";

export async function listEventsForFamily(familyId: string) {
  const events = await prisma.calendarEvent.findMany({
    where: { familyId },
    orderBy: { startsAt: "asc" }
  });

  return events.map((event) => ({
    id: event.id,
    familyId: event.familyId,
    title: event.title,
    description: event.description,
    startsAt: event.startsAt,
    endsAt: event.endsAt,
    visibility: event.visibility
  }));
}
