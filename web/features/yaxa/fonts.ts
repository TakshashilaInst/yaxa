/**
 * The Takshashila website's fonts: Inter for everything with words in it, Roboto Mono for
 * metadata (eyebrows, dates, buttons). next/font downloads them at build time and serves them
 * from Yaxa itself, so pages make no third-party font requests.
 */
import { Inter, Roboto_Mono } from "next/font/google";

const inter = Inter({ subsets: ["latin"], variable: "--tk-sans", display: "swap" });
const mono = Roboto_Mono({ subsets: ["latin"], variable: "--tk-mono", display: "swap" });

export const houseFonts = `${inter.variable} ${mono.variable}`;
