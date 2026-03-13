import bcrypt from "bcryptjs";
import { PrismaClient, MemberRole, TaskCadence, TaskStatus, Visibility } from "@prisma/client";

const prisma = new PrismaClient();

async function main() {
  await prisma.postLike.deleteMany();
  await prisma.postComment.deleteMany();
  await prisma.familyPost.deleteMany();
  await prisma.familyListItem.deleteMany();
  await prisma.familyList.deleteMany();
  await prisma.reminder.deleteMany();
  await prisma.calendarEvent.deleteMany();
  await prisma.householdTask.deleteMany();
  await prisma.locationCheckIn.deleteMany();
  await prisma.familyMember.deleteMany();
  await prisma.family.deleteMany();
  await prisma.user.deleteMany();

  const passwordHash = await bcrypt.hash(process.env.DEMO_USER_PASSWORD ?? "family123", 10);
  const caregiverHash = await bcrypt.hash("caregiver123", 10);

  const parent = await prisma.user.create({
    data: {
      email: process.env.DEMO_USER_EMAIL ?? "parent@example.com",
      passwordHash,
      displayName: "Avery Parent"
    }
  });

  const caregiver = await prisma.user.create({
    data: {
      email: "caregiver@example.com",
      passwordHash: caregiverHash,
      displayName: "Sam Caregiver"
    }
  });

  const riverHouse = await prisma.family.create({
    data: {
      slug: "river-house",
      name: "River House",
      timezone: "America/Los_Angeles",
      locationSharingEnabled: true
    }
  });

  const hillHouse = await prisma.family.create({
    data: {
      slug: "hill-house",
      name: "Hill House",
      timezone: "America/New_York",
      locationSharingEnabled: false
    }
  });

  await prisma.familyMember.createMany({
    data: [
      {
        familyId: riverHouse.id,
        userId: parent.id,
        role: MemberRole.OWNER,
        permissions: {
          canManageMembers: true,
          canManageTasks: true,
          canViewLocation: true,
          canModerateFeed: true
        }
      },
      {
        familyId: riverHouse.id,
        userId: caregiver.id,
        role: MemberRole.CAREGIVER,
        permissions: {
          canManageTasks: true,
          canViewLocation: true,
          canPost: true
        }
      },
      {
        familyId: hillHouse.id,
        userId: parent.id,
        role: MemberRole.ADMIN,
        permissions: {
          canManageMembers: false,
          canManageTasks: true,
          canViewLocation: false,
          canPost: true
        }
      }
    ]
  });

  await prisma.householdTask.createMany({
    data: [
      {
        familyId: riverHouse.id,
        createdById: parent.id,
        assigneeId: caregiver.id,
        title: "Take out recycling",
        description: "Blue bin goes out before 7am on Tuesday.",
        cadence: TaskCadence.WEEKLY,
        status: TaskStatus.OPEN,
        visibility: Visibility.SHARED
      },
      {
        familyId: riverHouse.id,
        createdById: parent.id,
        title: "Approve camp form",
        description: "One-time admin reminder for this week.",
        cadence: TaskCadence.ONE_TIME,
        status: TaskStatus.OPEN,
        visibility: Visibility.PRIVATE
      },
      {
        familyId: hillHouse.id,
        createdById: parent.id,
        title: "Restock pantry list",
        cadence: TaskCadence.DAILY,
        status: TaskStatus.DONE,
        visibility: Visibility.SHARED
      }
    ]
  });

  await prisma.calendarEvent.createMany({
    data: [
      {
        familyId: riverHouse.id,
        title: "Soccer practice",
        description: "Bring water and shin guards.",
        startsAt: new Date("2026-03-12T17:30:00.000Z"),
        endsAt: new Date("2026-03-12T19:00:00.000Z"),
        visibility: Visibility.SHARED
      },
      {
        familyId: hillHouse.id,
        title: "Parent-teacher conference",
        startsAt: new Date("2026-03-14T14:00:00.000Z"),
        endsAt: new Date("2026-03-14T14:30:00.000Z"),
        visibility: Visibility.PRIVATE
      }
    ]
  });

  const groceryList = await prisma.familyList.create({
    data: {
      familyId: riverHouse.id,
      title: "Weekend groceries",
      visibility: Visibility.SHARED
    }
  });

  await prisma.familyListItem.createMany({
    data: [
      { listId: groceryList.id, label: "Milk", completed: false },
      { listId: groceryList.id, label: "Oranges", completed: true }
    ]
  });

  await prisma.reminder.createMany({
    data: [
      {
        familyId: riverHouse.id,
        recipientId: caregiver.id,
        title: "Check school pickup plan",
        scheduleText: "Every weekday at 14:30"
      },
      {
        familyId: hillHouse.id,
        recipientId: parent.id,
        title: "Review shared budget",
        scheduleText: "Every Friday at 18:00"
      }
    ]
  });

  const riverPost = await prisma.familyPost.create({
    data: {
      familyId: riverHouse.id,
      authorId: parent.id,
      body: "Field trip slips are uploaded. Please confirm by tonight.",
      mediaUrl: "https://example.invalid/field-trip-slip.pdf"
    }
  });

  await prisma.postComment.create({
    data: {
      postId: riverPost.id,
      authorId: caregiver.id,
      body: "Confirmed. I can handle pickup if needed."
    }
  });

  await prisma.postLike.create({
    data: {
      postId: riverPost.id,
      userId: caregiver.id
    }
  });

  await prisma.locationCheckIn.create({
    data: {
      familyId: riverHouse.id,
      userId: caregiver.id,
      label: "School pickup line",
      latitude: 34.0522,
      longitude: -118.2437
    }
  });
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
