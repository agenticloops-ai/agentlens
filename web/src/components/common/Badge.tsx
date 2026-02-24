import clsx from "clsx";

type BadgeProps = {
  children: React.ReactNode;
  variant?: "default" | "green" | "orange" | "blue" | "red" | "purple";
  size?: "sm" | "md";
};

const variantClasses: Record<NonNullable<BadgeProps["variant"]>, string> = {
  default: "bg-gray-700 text-gray-300",
  green: "bg-green-900/60 text-green-300",
  orange: "bg-orange-900/60 text-orange-300",
  blue: "bg-blue-900/60 text-blue-300",
  red: "bg-red-900/60 text-red-300",
  purple: "bg-purple-900/60 text-purple-300",
};

const sizeClasses: Record<NonNullable<BadgeProps["size"]>, string> = {
  sm: "px-1.5 py-0.5 text-[10px]",
  md: "px-2 py-0.5 text-xs",
};

export function Badge({
  children,
  variant = "default",
  size = "md",
}: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full font-medium whitespace-nowrap",
        variantClasses[variant],
        sizeClasses[size],
      )}
    >
      {children}
    </span>
  );
}
