import {NextResponse} from "next/server";
import {supabaseServer} from "../../../../lib/supabase-server";
import {supabaseAdmin} from "../../../../lib/supabase-admin";
import {encryptSecret} from "../../../../lib/crypto";
export async function GET(req:Request){
 const u=new URL(req.url),code=u.searchParams.get("code");if(!code)return NextResponse.json({error:"Missing Google authorization code"},{status:400});
 const auth=await supabaseServer();const {data:{user}}=await auth.auth.getUser();if(!user)return NextResponse.redirect(new URL("/login",u.origin));
 const redirect=process.env.YOUTUBE_REDIRECT_URI||new URL("/api/auth/youtube/callback",u.origin).toString();
 const body=new URLSearchParams({code,client_id:process.env.YOUTUBE_CLIENT_ID||"",client_secret:process.env.YOUTUBE_CLIENT_SECRET||"",redirect_uri:redirect,grant_type:"authorization_code"});
 const token=await fetch("https://oauth2.googleapis.com/token",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body}).then(r=>r.json());
 if(!token.access_token)return NextResponse.json({error:"YouTube token exchange failed",details:token},{status:502});
 const db=supabaseAdmin();await db.from("clipilot_connections").upsert({user_id:user.id,provider:"youtube",access_token_enc:encryptSecret(token.access_token),refresh_token_enc:token.refresh_token?encryptSecret(token.refresh_token):null,expires_at:token.expires_in?new Date(Date.now()+token.expires_in*1000).toISOString():null,scopes:["https://www.googleapis.com/auth/youtube.upload"],updated_at:new Date().toISOString()},{onConflict:"user_id,provider"});
 return NextResponse.redirect(new URL("/dashboard?youtube=connected",u.origin));
}