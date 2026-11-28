import type { Metadata } from "next";

import { houseFonts } from "@/features/yaxa/fonts";
import "./learn/yaxa-learn.css";

export const metadata: Metadata = {
  title: "Yaxa · Takshashila",
  description: "Learn public policy, personalised to your field.",
};

/** Yaxa Learn has its own chrome: no DeepTutor sidebar. The wrapper only carries the font variables. */
export default function LearnLayout({ children }: { children: React.ReactNode }) {
  return <div className={houseFonts} style={{ display: "contents" }}>{children}</div>;
}
