import { type ButtonHTMLAttributes, forwardRef } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";

type Variant = "primary" | "secondary" | "outline" | "ghost" | "danger" | "dangerGhost";
type Size = "sm" | "md" | "lg" | "icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: React.ReactNode;
}

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-brand-600 text-white shadow-xs hover:bg-brand-700 focus-visible:ring-brand-300 disabled:bg-brand-300",
  secondary:
    "bg-gray-900 text-white shadow-xs hover:bg-gray-800 focus-visible:ring-gray-400 disabled:bg-gray-400",
  outline:
    "bg-white text-gray-700 border border-gray-300 shadow-xs hover:bg-gray-50 focus-visible:ring-gray-300 disabled:text-gray-400",
  ghost: "bg-transparent text-gray-600 hover:bg-gray-100 focus-visible:ring-gray-300 disabled:text-gray-300",
  danger:
    "bg-danger-600 text-white shadow-xs hover:bg-danger-700 focus-visible:ring-danger-300 disabled:bg-danger-300",
  dangerGhost:
    "bg-transparent text-danger-600 hover:bg-danger-50 focus-visible:ring-danger-200 disabled:text-danger-300",
};

const sizeClasses: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-9 px-3.5 text-sm gap-2",
  lg: "h-11 px-5 text-sm gap-2",
  icon: "h-9 w-9 p-0 justify-center",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, icon, children, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center rounded-lg font-medium transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-4",
          "disabled:cursor-not-allowed",
          variantClasses[variant],
          sizeClasses[size],
          className
        )}
        {...props}
      >
        {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";
