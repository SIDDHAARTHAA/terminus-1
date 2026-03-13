import dotenv from "dotenv";
import { z } from "zod";

dotenv.config();

const configSchema = z.object({
  DATABASE_URL: z.string().min(1),
  JWT_SECRET: z.string().min(8),
  PORT: z.coerce.number().int().positive().default(3000),
  DEMO_USER_EMAIL: z.string().email().default("parent@example.com"),
  DEMO_USER_PASSWORD: z.string().min(8).default("family123")
});

export const config = configSchema.parse(process.env);
