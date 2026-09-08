"use client";
import {AuthProvider,Protected} from "@/features/auth/auth";
export default function Layout({children}:{children:React.ReactNode}){return <AuthProvider><Protected>{children}</Protected></AuthProvider>}
