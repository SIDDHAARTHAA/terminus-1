import { NextFunction, Response } from "express";

import { verifyToken } from "../modules/auth/service";
import { AuthenticatedRequest, AuthTokenPayload } from "../types/auth";

export function authenticateRequest(req: AuthenticatedRequest, res: Response, next: NextFunction) {
  const authorization = req.header("authorization");
  if (!authorization || !authorization.startsWith("Bearer ")) {
    res.status(401).json({ error: "Missing bearer token" });
    return;
  }

  try {
    req.auth = verifyToken(authorization.slice("Bearer ".length));
    next();
  } catch (error) {
    res.status(401).json({ error: "Invalid bearer token", detail: (error as Error).message });
  }
}

export function ensureFamilyMembership(auth: AuthTokenPayload, familyId: string) {
  const membership = auth.memberships.find((item) => item.familyId === familyId);
  if (!membership) {
    throw new Error("You do not belong to that family");
  }

  return membership;
}
