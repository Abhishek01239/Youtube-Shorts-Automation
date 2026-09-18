import {NextResponse} from "next/server";
import {supabaseServer} from "../../../../lib/supabase-server";
import {supabaseAdmin} from "../../../../lib/supabase-admin";
import {encryptSecret} from "../../../../lib/crypto";
export async function GET(req:Request){
 const u=new URL(req.url),code=u.searchParams.get("code");if(!code)return NextResponse.json({error:"Missing Twitch authorization code"},{status:400});
 const auth=await supabaseServer();const {data:{user}}=await auth.auth.getUser();if(!user)return NextResponse.redirect(new URL("/login",u.origin));
 const redirect=process.env.TWITCH_REDIRECT_URI||new URL("/api/auth/twitch/callback",u.origin).toString();
 const body=new URLSearchParams({client_id:process.env.TWITCH_CLIENT_ID||"",client_secret:process.env.TWITCH_CLIENT_SECRET||"",code,grant_type:"authorization_code",redirect_uri:redirect});
 const token=await fetch("https://id.twitch.tv/oauth2/token",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body}).then(r=>r.json());
 if(!token.access_token)return NextResponse.json({error:"Twitch token exchange failed",details:token},{status:502});
 const validate=await fetch("https://id.twitch.tv/oauth2/validate",{headers:{Authorization:"OAuth "+token.access_token}}).then(r=>r.json());
 const db=supabaseAdmin();await db.from("clipilot_connections").upsert({user_id:user.id,provider:"twitch",access_token_enc:encryptSecret(token.access_token),refresh_token_enc:token.refresh_token?encryptSecret(token.refresh_token):null,expires_at:token.expires_in?new Date(Date.now()+token.expires_in*1000).toISOString():null,scopes:token.scope||[],provider_user_id:validate.user_id||null,provider_channel_name:validate.login||null,updated_at:new Date().toISOString()},{onConflict:"user_id,provider"});
 return NextResponse.redirect(new URL("/dashboard?twitch=connected",u.origin));
}