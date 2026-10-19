// Margin buttons (STYLEGUIDE §6): primary, secondary, tertiary, highlight (student screens only) and destructive, in
// small (36px), medium (44px, default) and large (52px). Loading keeps the width, shows a spinner and a present-tense
// label, and sets aria-busy.
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "relative inline-flex flex-none select-none items-center justify-center gap-2 whitespace-nowrap rounded-sm border font-sans font-medium no-underline " +
    "transition-colors duration-150 disabled:cursor-not-allowed [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "border-transparent bg-ink-600 text-white hover:bg-ink-700 hover:text-white active:bg-ink-800 active:shadow-[inset_0_2px_4px_rgba(19,35,74,.25)] " +
          "disabled:border-transparent disabled:bg-slate-100 disabled:text-slate-400 disabled:shadow-none",
        secondary:
          "border-slate-200 bg-white text-ink-700 hover:border-ink-200 hover:bg-ink-50 hover:text-ink-700 active:border-ink-300 active:bg-ink-100 " +
          "disabled:border-slate-100 disabled:bg-white disabled:text-slate-300",
        tertiary:
          "border-transparent bg-transparent text-ink-600 hover:bg-ink-50 hover:text-ink-600 active:bg-ink-100 disabled:bg-transparent disabled:text-slate-300",
        highlight:
          "border-hl-border bg-hl-300 font-semibold text-ink-900 hover:bg-hl-border hover:text-ink-900 active:bg-hl-500 " +
          "disabled:border-transparent disabled:bg-slate-100 disabled:text-slate-400",
        destructive:
          "border-transparent bg-danger text-white hover:bg-danger-hover hover:text-white active:bg-danger-pressed " +
          "disabled:bg-slate-100 disabled:text-slate-400",
        link:
          "h-auto border-0 bg-transparent p-0 text-ink-600 underline decoration-1 underline-offset-[3px] hover:text-ink-700 disabled:text-slate-400",
      },
      size: {
        sm: "h-9 px-3 text-control-sm [&_svg]:size-4",
        md: "h-11 px-[18px] text-body [&_svg]:size-5",
        lg: "h-[52px] rounded-[10px] px-[22px] text-control-lg [&_svg]:size-5",
        "icon-sm": "size-9 p-0 [&_svg]:size-4",
        icon: "size-11 p-0 [&_svg]:size-5",
        "icon-lg": "size-[52px] rounded-[10px] p-0 [&_svg]:size-5",
      },
    },
    compoundVariants: [{ variant: "link", className: "h-auto px-0" }],
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** Shows a spinner and `loadingLabel` (present tense, e.g. "Evaluating") while keeping the button's width. */
  loading?: boolean;
  loadingLabel?: string;
  /** Leading icon; reduces the left padding by 4px as in the guide. */
  icon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, loading, loadingLabel, icon, disabled, children, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    const iconOnly = size === "icon" || size === "icon-sm" || size === "icon-lg";
    const lead = icon && !iconOnly ? (size === "sm" ? "pl-2" : size === "lg" ? "pl-[18px]" : "pl-[14px]") : "";
    if (asChild) {
      return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), lead, className)} {...props}>{children}</Comp>;
    }
    return (
      <button
        ref={ref}
        type={type ?? "button"}
        className={cn(buttonVariants({ variant, size }), lead, className)}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading ? (
          <>
            {/* the hidden original content keeps the button's width */}
            <span className="invisible inline-flex items-center gap-2" aria-hidden>{icon}{children}</span>
            <span className="absolute inset-0 inline-flex items-center justify-center gap-2">
              <Loader2 className="animate-spin" aria-hidden />
              {!iconOnly && <span>{loadingLabel ?? children}</span>}
            </span>
          </>
        ) : (
          <>
            {icon}
            {children}
          </>
        )}
      </button>
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
