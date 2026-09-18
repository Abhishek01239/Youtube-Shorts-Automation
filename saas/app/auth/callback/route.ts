import {NextResponse} from "next/server";
import {supabaseServer} from "../../../lib/supabase-server";
export async function GET(req:Request){const u=new URL(req.url),code=u.searchParams.get("code");if(code){const s=await supabaseServer();await s.auth.exchangeCodeForSession(code)}return NextResponse.redirect(new URL("/dashboard",u.origin));}