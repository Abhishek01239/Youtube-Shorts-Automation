import {NextResponse} from "next/server";
export async function GET(req:Request){
 const u=new URL(req.url); const code=u.searchParams.get("code"); if(!code)return NextResponse.json({error:"Missing Google authorization code"},{status:400});
 const redirect=process.env.YOUTUBE_REDIRECT_URI||new URL("/api/auth/youtube/callback",u.origin).toString();
 const body=new URLSearchParams({code,client_id:process.env.YOUTUBE_CLIENT_ID||"",client_secret:process.env.YOUTUBE_CLIENT_SECRET||"",redirect_uri:redirect,grant_type:"authorization_code"});
 const token=await fetch("https://oauth2.googleapis.com/token",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body}).then(r=>r.json());
 if(!token.access_token)return NextResponse.json({error:"YouTube token exchange failed",details:token},{status:502});
 // Production TODO: encrypt and persist refresh token against the authenticated customer.
 return NextResponse.redirect(new URL("/dashboard?youtube=connected",u.origin));
}