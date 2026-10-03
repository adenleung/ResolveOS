import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ButtonHTMLAttributes, ReactNode } from "react";
export function cn(...values: Parameters<typeof clsx>) { return twMerge(clsx(...values)); }
const variants = cva("button", { variants: { variant: { default: "button-primary", secondary: "button-secondary", danger: "button-danger", ghost: "button-ghost" } }, defaultVariants: {variant: "default"} });
export function Button({className, variant, asChild, ...props}: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof variants> & {asChild?: boolean}) { const Component = asChild ? Slot : "button"; return <Component className={cn(variants({variant}), className)} {...props} />; }
export function Card({title, description, children, action, className}: {title?: string; description?: string; children: ReactNode; action?: ReactNode; className?: string}) { return <section className={cn("card", className)}>{title && <div className="card-heading"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>}{children}</section>; }
export function Badge({value}: {value: string}) { const color = /^(NO |NOT_|NOT |INACTIVE|UNAVAILABLE|INSUFFICIENT)/.test(value) ? "blue" : /BLOCK|FAIL|REJECT|REVOK|ESCALAT|DEAD/.test(value) ? "red" : /RESOLVED|VERIFIED|AUTO_ELIGIBLE|ACTIVE|COMPLETED|APPROVED|PASS/.test(value) ? "green" : /HUMAN|PENDING|OPEN|WAIT|INVESTIGAT/.test(value) ? "amber" : "blue"; return <span className={`badge ${color}`}>{value.replaceAll("_", " ")}</span>; }
export function Empty({children}: {children?: ReactNode}) { return <div className="empty"><span className="empty-mark">○</span><strong>No records to display</strong><p>{children ?? "No matching persisted records are available."}</p></div>; }
