import { z } from "zod";

export const emailField = z.string().trim().min(1, "Enter your email.").email("Enter a valid email address.");
export const newPasswordField = z
  .string()
  .min(8, "Use at least 8 characters.")
  .max(256, "Use at most 256 characters.")
  .refine((v) => v.trim().length > 0, "Password cannot be blank.");

export const loginSchema = z.object({ email: emailField, password: z.string().min(1, "Enter your password.") });

export const signupSchema = z
  .object({ email: emailField, password: newPasswordField, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { message: "Passwords don't match.", path: ["confirm"] });

export const resetSchema = z
  .object({ password: newPasswordField, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { message: "Passwords don't match.", path: ["confirm"] });
