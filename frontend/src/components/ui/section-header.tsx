import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface SectionHeaderProps {
  badge?: string;
  title: string;
  subtitle?: string;
  className?: string;
  align?: "center" | "left";
}

export function SectionHeader({
  badge,
  title,
  subtitle,
  className,
  align = "center",
}: SectionHeaderProps) {
  return (
    <div className={cn("mb-14", align === "center" && "text-center", className)}>
      {badge && (
        <Badge className="mb-4 bg-primary/10 text-primary border-primary/25 hover:bg-primary/15">
          {badge}
        </Badge>
      )}
      <h2
        className="text-3xl lg:text-4xl font-extrabold text-foreground mb-3"
        style={{ fontFamily: "var(--font-display)" }}
      >
        {title}
      </h2>
      {subtitle && (
        <p
          className={cn(
            "text-muted-foreground text-lg leading-relaxed",
            align === "center" && "max-w-2xl mx-auto",
          )}
        >
          {subtitle}
        </p>
      )}
    </div>
  );
}
