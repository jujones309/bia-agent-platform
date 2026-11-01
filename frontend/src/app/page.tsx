import { redirect } from "next/navigation";
import { Route } from "@/lib/routes";

/** Sends the root of the site to the inventory of agents. */
export default function HomePage(): never {
  redirect(Route.AGENTS);
}
