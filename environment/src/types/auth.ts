import { Request } from "express";

export type MembershipClaim = {
  familyId: string;
  role: string;
};

export type AuthTokenPayload = {
  sub: string;
  email: string;
  memberships: MembershipClaim[];
  iat?: number;
  exp?: number;
};

export type AuthenticatedRequest = Request & {
  auth?: AuthTokenPayload;
};
