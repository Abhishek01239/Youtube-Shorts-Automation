import {NextResponse} from "next/server";
export async function GET(req:Request){
 const u=new URL(req.url); const code=u.searchParams.get("code"); if(!code)return NextResponse.json({error:"Missing Twitch authorization code"},{status:400});
 const redirect=process.env.TWITCH_REDIRECT_URI||new URL("/api/auth/twitch/callback",u.origin).toString();
 const body=new URLSearchParams({client_id:process.env.TWITCH_CLIENT_ID||"",client_secret:process.env.TWITCH_CLIENT_SECRET||"",code,grant_type:"authorization_code",redirect_uri:redirect});
 const token=await fetch("https://id.twitch.tv/oauth2/token",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body}).then(r=>r.json());
 if(!token.access_token)return NextResponse.json({error:"Twitch token exchange failed",details:token},{status:502});
 // Production TODO: encrypt and persist token against the authenticated customer.
 return NextResponse.redirect(new URL("/dashboard?twitch=connected",u.origin));
}