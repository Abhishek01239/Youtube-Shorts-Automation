# ClipPilot worker

The SaaS database queues customer jobs in the clipilot_jobs table.

Worker responsibilities:
1. claim one job with the service-role function clipilot_claim_job(worker_id);
2. load the customer's enabled settings;
3. obtain and decrypt that customer's Twitch and YouTube OAuth tokens;
4. run the existing Python pipeline with a generated per-customer channel configuration;
5. write results to clipilot_uploads and mark the job succeeded/failed.

Never expose the Supabase service-role key or OAuth refresh tokens to browser code.

The existing root pipeline.py is reused as the processing engine.