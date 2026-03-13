import { Router } from "express";

import { login } from "../modules/auth/service";

export const authRouter = Router();

authRouter.post("/api/v1/auth/login", async (req, res) => {
  try {
    const result = await login(req.body);
    res.json({ ok: true, ...result });
  } catch (error) {
    const message = (error as Error).message;
    res.status(message === "Invalid email or password" ? 401 : 400).json({
      error: message
    });
  }
});
