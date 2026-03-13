import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { z } from "zod";

import { config } from "../../lib/config";
import { prisma } from "../../lib/prisma";
import { AuthTokenPayload } from "../../types/auth";

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1)
});

export async function login(input: unknown) {
  const { email, password } = loginSchema.parse(input);
  const user = await prisma.user.findUnique({
    where: { email },
    include: {
      memberships: {
        include: { family: true },
        orderBy: { createdAt: "asc" }
      }
    }
  });

  if (!user) {
    throw new Error("Invalid email or password");
  }

  const passwordOk = await bcrypt.compare(password, user.passwordHash);
  if (!passwordOk) {
    throw new Error("Invalid email or password");
  }

  const payload: AuthTokenPayload = {
    sub: user.id,
    email: user.email,
    memberships: user.memberships.map((membership) => ({
      familyId: membership.familyId,
      role: membership.role
    }))
  };

  const accessToken = jwt.sign(payload, config.JWT_SECRET, {
    expiresIn: "8h",
    subject: user.id
  });

  return {
    accessToken,
    user: {
      id: user.id,
      email: user.email,
      displayName: user.displayName
    },
    memberships: user.memberships.map((membership) => ({
      familyId: membership.familyId,
      familyName: membership.family.name,
      role: membership.role,
      permissions: membership.permissions
    }))
  };
}

export function verifyToken(token: string): AuthTokenPayload {
  return jwt.verify(token, config.JWT_SECRET) as AuthTokenPayload;
}
