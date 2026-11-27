import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import * as React from "react";

import { cn } from "@/lib/utils";

export const RadioGroup = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Root>
>(({ className, ...props }, ref) => (
  <RadioGroupPrimitive.Root ref={ref} className={cn("grid gap-2", className)} {...props} />
));
RadioGroup.displayName = "RadioGroup";

/** A pill-style option, filled when selected (matches the old radio styling). */
export const RadioPill = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <RadioGroupPrimitive.Item
    ref={ref}
    className={cn(
      "rounded-btn border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-card-alt data-[state=checked]:border-selection data-[state=checked]:bg-selection data-[state=checked]:text-on-selection",
      className,
    )}
    {...props}
  >
    {children}
  </RadioGroupPrimitive.Item>
));
RadioPill.displayName = "RadioPill";
