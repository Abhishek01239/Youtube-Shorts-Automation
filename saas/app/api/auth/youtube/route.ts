import {NextResponse} from "next/server";
export async function GET(req:Request){
 const u=new URL(req.url); const client=process.env.YOUTUBE_CLIENT_ID; const redirect=process.env.YOUTUBE_REDIRECT_URI||new URL("/api/auth/youtube/callback",u.origin).toString();
 if(!client)return NextResponse.json({error:"YOUTUBE_CLIENT_ID is not configured"},{status:503});
 const p=new URLSearchParams({client_id:client,redirect_uri:redirect,response_type:"code",access_type:"offline",prompt:"consent",scope:"https://www.googleapis.com/auth/youtube.upload"});
 return NextResponse.redirect("https://accounts.google.com/o/oauth2/v2/auth?"+p.toString());
}