import type { Metadata } from "next";
import "./learn/yaxa-learn.css";

export const metadata: Metadata = {
  title: "Yaxa · Takshashila",
  description: "Learn public policy, personalised to your field.",
};

/** Yaxa Learn has its own chrome: no DeepTutor sidebar. */
export default function LearnLayout({ children }: { children: React.ReactNode }) {
  return children;
}
