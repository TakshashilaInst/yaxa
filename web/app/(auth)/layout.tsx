import { houseFonts } from "@/features/yaxa/fonts";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={`${houseFonts} min-h-screen flex items-center justify-center bg-[var(--background)]`}>
      {children}
    </div>
  );
}
