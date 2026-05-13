# Tour Producer

ECS one-shot task that collects travel tour data from the Viator Partner API and stores it in S3.

## Overview

The Tour Producer runs on a scheduled EventBridge rule (every 24 hours). For each supported currency it:

1. Looks up the associated country (e.g., JPY → Japan)
2. Calls the Viator Partner API to fetch tour listings for that country
3. Normalizes raw tour data into a canonical JSON schema
4. Downloads tour images and uploads them to S3 (`tours/images/{currency_code}/{id}.jpg`)
5. Uploads tour JSON to S3 (`tours/{currency_code}/tour-{id}.json`)

If the Viator API fails for a currency, fallback tour data is used and existing S3 data is retained if no fallback exists.

## S3 Layout

```
s3://{S3_TOUR_BUCKET}/
  tours/
    USD/
      tour-abc123.json
      tour-def456.json
    JPY/
      tour-xyz789.json
  tours/images/
    USD/
      abc123.jpg
    JPY/
      xyz789.jpg
```

## Tour JSON Schema

```json
{
  "id":            "abc123def456",
  "name":          "New York City Highlights Tour",
  "description":   "Explore the best of NYC...",
  "image_url":     "https://media.tacdn.com/...",
  "image_key":     "tours/images/USD/abc123def456.jpg",
  "affiliate_url": "https://www.viator.com/tours/...",
  "currency_code": "USD",
  "country_code":  "US",
  "country_name":  "United States",
  "collected_at":  "2026-05-09T00:00:00+00:00"
}
```

## Configuration

Copy `.env.example` to `.env` and fill in the values:

| Variable | Required | Default | Description |
|---|---|---|---|
| `VIATOR_API_KEY` | ✅ | — | Viator Partner API key |
| `S3_TOUR_BUCKET` | ✅ | — | S3 bucket name for tour data |
| `SUPPORTED_CURRENCIES` | | `USD,EUR,...` | Comma-separated currency codes |
| `MAX_TOURS_PER_CURRENCY` | | `10` | Max tours fetched per currency |
| `AWS_REGION` | | `ap-southeast-1` | AWS region |

## Local Development

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in VIATOR_API_KEY and S3_TOUR_BUCKET
python tour_producer.py
```

## Docker

```bash
# Build
docker build -t tour-producer .

# Run
docker run --env-file .env tour-producer
```

## Push to ECR

```bash
aws ecr get-login-password --region ap-southeast-1 | \
  docker login --username AWS --password-stdin \
  {account_id}.dkr.ecr.ap-southeast-1.amazonaws.com

docker tag tour-producer:latest \
  {account_id}.dkr.ecr.ap-southeast-1.amazonaws.com/tour_producer_repo:latest

docker push \
  {account_id}.dkr.ecr.ap-southeast-1.amazonaws.com/tour_producer_repo:latest
```
