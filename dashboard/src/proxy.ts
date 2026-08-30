import { clerkMiddleware } from "@clerk/nextjs/server";

export default clerkMiddleware();

export const config = {
  // /status is deliberately excluded - it's a public page, no auth.
  matcher: ["/((?!_next|status|.*\\..*).*)", "/(api|trpc)(.*)"],
};