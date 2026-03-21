# Deploying to Render.com

This guide covers deploying notifications-api to [Render.com](https://render.com) as an alternative to cloud.gov. The existing Cloud Foundry deployment is preserved — Render support is additive.

## Architecture

| Component | Render Service | Plan | Monthly Cost |
|-----------|---------------|------|-------------|
| Web (gunicorn + Flask) | Web Service | Starter (512MB) | $7 |
| Celery worker | Background Worker | Starter (512MB) | $7 |
| Celery beat scheduler | Background Worker | Starter (512MB) | $7 |
| PostgreSQL | Render PostgreSQL | Starter (256MB, 1GB) | $7 |
| Redis | Render Redis | Free (25MB) | $0 |
| **Total** | | | **~$28/mo** |

Plus AWS costs for SES (email), SNS (SMS), and S3 (CSV uploads) — usage-based.

## Prerequisites

1. A [Render account](https://render.com)
2. An AWS account with SES, SNS, and S3 configured in us-west-2
3. SES domain verified for sending email
4. SNS configured for SMS sending
5. An S3 bucket for CSV uploads

## Deploy

### Option A: Blueprint (recommended)

1. Fork this repo to your GitHub account
2. In Render dashboard, click **New > Blueprint**
3. Connect your GitHub repo
4. Render reads `render.yaml` and provisions all services
5. Set the `sync: false` env vars in the Render dashboard:
   - `API_HOST_NAME` — your Render web service URL (e.g. `https://notify-api.onrender.com`)
   - `ADMIN_BASE_URL` — URL of the notifications-admin app
   - `AWS_US_TOLL_FREE_NUMBER` — your toll-free SMS number
   - `SES_AWS_ACCESS_KEY_ID` / `SES_AWS_SECRET_ACCESS_KEY` — SES credentials
   - `SES_DOMAIN_ARN` — your verified SES domain ARN
   - `SNS_AWS_ACCESS_KEY_ID` / `SNS_AWS_SECRET_ACCESS_KEY` — SNS credentials
   - `CSV_AWS_ACCESS_KEY_ID` / `CSV_AWS_SECRET_ACCESS_KEY` — S3 credentials
   - `CSV_BUCKET_NAME` — your S3 bucket name

### Option B: Manual

Create each service individually in the Render dashboard matching the `render.yaml` configuration.

## How It Works

The runtime detection is in `app/cloudfoundry_config.py`:

- If `RENDER=true` env var is set → uses `app/render_config.py` (reads standard env vars)
- Otherwise → uses `CloudfoundryConfig` (reads VCAP_SERVICES for Cloud Foundry)

Both adapters expose the same interface. `app/config.py` has a small addition: `Production.CSV_UPLOAD_BUCKET` falls back to env vars when the Cloud Foundry bucket is empty (i.e., on Render).

## Scaling Up

When load requires it, upgrade services in the Render dashboard:

| Load | Web | Worker | PostgreSQL | Redis |
|------|-----|--------|------------|-------|
| Light (<1K msgs/day) | Starter $7 | Starter $7 | Starter $7 | Free |
| Medium (<10K msgs/day) | Standard $25 | Standard $25 | Standard $50 | Standard $32 |
| Heavy (<100K msgs/day) | Pro $85 | Pro x2 $170 | Pro $175 | Pro $95 |

## Differences from cloud.gov

- **No egress proxy** — outbound traffic is unrestricted
- **No FedRAMP** — not suitable for customers requiring FedRAMP authorization
- **No New Relic** — omit `NEW_RELIC_LICENSE_KEY` to skip; gunicorn runs without the NR wrapper
- **No StatsD** — omit `STATSD_HOST`; gunicorn skips StatsD reporting
- **Migrations** — run in the build command (`flask db upgrade`) instead of at web startup
- **Single web instance** — Starter plan; scale to multiple instances on Standard+ plans
