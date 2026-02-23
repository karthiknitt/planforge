import { cn } from "@/lib/utils";

interface SectionWrapperProps {
  children: React.ReactNode;
  className?: string;
  id?: string;
  narrow?: boolean;
}

export function SectionWrapper({ children, className, id, narrow }: SectionWrapperProps) {
  return (
    <section id={id} className={cn("py-20 relative", className)}>
      <div className={cn("mx-auto px-4 sm:px-6 lg:px-8", narrow ? "max-w-4xl" : "max-w-7xl")}>
        {children}
      </div>
    </section>
  );
}
