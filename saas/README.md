# ClipPilot SaaS MVP

Twitch → AI processing → YouTube Shorts automation SaaS layer for the existing Python pipeline.

## What is implemented

- Next.js SaaS landing page
- ₹99/month Razorpay subscription checkout
- Twitch OAuth connection
- YouTube OAuth connection with the upload scope
- Customer dashboard
- Environment-variable based secrets
- Keeps the existing Python video pipeline as the processing engine

## Local run

```bash
cd saas
cp .env.example .env.local
npm install
npm run dev
```

Required environment variables are listed in `.env.example`.

## Razorpay

Create a monthly Razorpay plan for ₹99 and put its plan ID in `RAZORPAY_PLAN_ID`. The API route creates a subscription and returns Razorpay's hosted checkout URL.

For production, add a verified Razorpay webhook before enabling a customer's automation. Do not activate service from a browser redirect alone.

## OAuth

Set Twitch and Google OAuth redirect URLs to:

- `https://YOUR_DOMAIN/api/auth/twitch/callback`
- `https://YOUR_DOMAIN/api/auth/youtube/callback`

The current callbacks prove the OAuth exchange. Production persistence must encrypt tokens and associate them with an authenticated customer account.

## Deployment

Deploy the `saas` directory as the Vercel project root. The original Python/GitHub Actions automation remains in the repository and can be invoked by a separate worker/queue in the next phase.

## Next phase

1. Add customer authentication + database.
2. Encrypt/persist Twitch and YouTube refresh tokens.
3. Add Razorpay webhook and subscription state machine.
4. Create per-customer worker jobs.
5. Connect worker jobs to the existing `pipeline.py`.
6. Add usage limits, history, retries and logs.
