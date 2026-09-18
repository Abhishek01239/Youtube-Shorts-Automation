import {NextResponse} from "next/server";
export async function GET(req:Request){
 const u=new URL(req.url); const client=process.env.TWITCH_CLIENT_ID; const redirect=process.env.TWITCH_REDIRECT_URI||new URL("/api/auth/twitch/callback",u.origin).toString();
 if(!client)return NextResponse.json({error:"TWITCH_CLIENT_ID is not configured"},{status:503});
 const p=new URLSearchParams({client_id:client,redirect_uri:redirect,response_type:"code",scope:"user:read:email"});
 return NextResponse.redirect("https://id.twitch.tv/oauth2/authorize?"+p.toString());
}