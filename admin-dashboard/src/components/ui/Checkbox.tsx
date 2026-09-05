import { type InputHTMLAttributes, forwardRef } from "react";
import { Check, Minus } from "lucide-react";
import { cn } from "../../lib/utils";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  indeterminate?: boolean;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, indeterminate, checked, ...props }, ref) => {
    return (
      <label className={cn("relative inline-flex size-4 shrink-0 cursor-pointer items-center justify-center", className)}>
        <input
          ref={ref}
          type="checkbox"
          checked={checked}
          className="peer absolute size-4 cursor-pointer appearance-none rounded border border-gray-300 bg-white checked:border-brand-600 checked:bg-brand-600 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-100"
          {...props}
        />
        {indeterminate ? (
          <Minus className="pointer-events-none absolute size-3 text-white opacity-0 peer-checked:opacity-100" />
        ) : (
          <Check className="pointer-events-none absolute size-3 text-white opacity-0 peer-checked:opacity-100" />
        )}
      </label>
    );
  }
);
Checkbox.displayName = "Checkbox";
