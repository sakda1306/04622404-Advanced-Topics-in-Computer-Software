import { type ClassValue, clsx } from "clsx";

/** Shared class-name merge utility for components in /components/ui. */
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}
