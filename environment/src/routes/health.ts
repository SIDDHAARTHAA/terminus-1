import { Router } from "express";

import { config } from "../lib/config";

export const healthRouter = Router();

healthRouter.get("/healthz", (_req, res) => {
  res.json({
    ok: true,
    service: "familyhub-api",
    demoCredentials: {
      email: config.DEMO_USER_EMAIL,
      password: config.DEMO_USER_PASSWORD
    }
  });
});
