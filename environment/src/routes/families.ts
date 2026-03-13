import { Router } from "express";

import { ensureFamilyMembership, authenticateRequest } from "../middleware/auth";
import { listEventsForFamily } from "../modules/events/service";
import {
  getFamilySummary,
  listFamiliesForUser,
  listFamilyLists,
  listFamilyReminders
} from "../modules/families/service";
import { listPostsForFamily } from "../modules/feed/service";
import { listTasksForFamily } from "../modules/tasks/service";
import { AuthenticatedRequest } from "../types/auth";

export const familyRouter = Router();

familyRouter.use(authenticateRequest);

familyRouter.get("/api/v1/families", async (req: AuthenticatedRequest, res, next) => {
  try {
    const families = await listFamiliesForUser(req.auth!.sub);
    res.json({ families });
  } catch (error) {
    next(error);
  }
});

familyRouter.get("/api/v1/families/:familyId/summary", async (req: AuthenticatedRequest, res, next) => {
  try {
    ensureFamilyMembership(req.auth!, req.params.familyId);
    const summary = await getFamilySummary(req.params.familyId, req.auth!.sub);
    if (!summary) {
      res.status(404).json({ error: "Family not found" });
      return;
    }
    res.json({ family: summary });
  } catch (error) {
    if ((error as Error).message === "You do not belong to that family") {
      res.status(403).json({ error: (error as Error).message });
      return;
    }
    next(error);
  }
});

familyRouter.get("/api/v1/families/:familyId/tasks", async (req: AuthenticatedRequest, res, next) => {
  try {
    ensureFamilyMembership(req.auth!, req.params.familyId);
    const tasks = await listTasksForFamily(req.params.familyId);
    res.json({ tasks });
  } catch (error) {
    if ((error as Error).message === "You do not belong to that family") {
      res.status(403).json({ error: (error as Error).message });
      return;
    }
    next(error);
  }
});

familyRouter.get("/api/v1/families/:familyId/events", async (req: AuthenticatedRequest, res, next) => {
  try {
    ensureFamilyMembership(req.auth!, req.params.familyId);
    const events = await listEventsForFamily(req.params.familyId);
    res.json({ events });
  } catch (error) {
    if ((error as Error).message === "You do not belong to that family") {
      res.status(403).json({ error: (error as Error).message });
      return;
    }
    next(error);
  }
});

familyRouter.get("/api/v1/families/:familyId/feed", async (req: AuthenticatedRequest, res, next) => {
  try {
    ensureFamilyMembership(req.auth!, req.params.familyId);
    const posts = await listPostsForFamily(req.params.familyId);
    res.json({ posts });
  } catch (error) {
    if ((error as Error).message === "You do not belong to that family") {
      res.status(403).json({ error: (error as Error).message });
      return;
    }
    next(error);
  }
});

familyRouter.get("/api/v1/families/:familyId/lists", async (req: AuthenticatedRequest, res, next) => {
  try {
    ensureFamilyMembership(req.auth!, req.params.familyId);
    const lists = await listFamilyLists(req.params.familyId);
    res.json({ lists });
  } catch (error) {
    if ((error as Error).message === "You do not belong to that family") {
      res.status(403).json({ error: (error as Error).message });
      return;
    }
    next(error);
  }
});

familyRouter.get("/api/v1/families/:familyId/reminders", async (req: AuthenticatedRequest, res, next) => {
  try {
    ensureFamilyMembership(req.auth!, req.params.familyId);
    const reminders = await listFamilyReminders(req.params.familyId);
    res.json({ reminders });
  } catch (error) {
    if ((error as Error).message === "You do not belong to that family") {
      res.status(403).json({ error: (error as Error).message });
      return;
    }
    next(error);
  }
});
