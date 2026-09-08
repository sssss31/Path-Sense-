import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata={title:"PathSense | Accessibility Intelligence",description:"Safer, more reliable logistics decisions for North-Eastern India."};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body><Providers>{children}</Providers></body></html>}

