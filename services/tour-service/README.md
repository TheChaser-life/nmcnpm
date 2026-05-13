# Tour Service

REST API service that serves travel tour information for each supported currency.
Reads tour JSON and images from S3 (written by Tour Producer) and returns them
with pre-signed image URLs.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check — returns `{"status": "ok"}` |
| GET | `/tours/{currency_code}` | List tours for a currency (e.g., `/tours/JPY`) |

### Response: GET /tours/{currency_code}

**With tours:**
```json
{
  "tours": [
    {
      "id": "abc123def456abcd",
      "name": "Tokyo City Tour",
      "description": "Explore the heart of Tokyo...",
      "image_url": "https://original-source.com/image.jpg",
      "image_key": "tours/images/JPY/abc123def456abcd.jpg",
      "image_presigned_url": "https://s3.amazonaws.com/bucket/tours/images/JPY/abc123def456abcd.jpg?...",
      "affiliate_url": "https://travelpayouts.com/...",
      "currency_code": "JPY",
      "country_code": "JP",
      "country_name": "Japan",
      "collected_at": "2024-01-15T17:00:00+00:00"
    }
  ],
  "count": 1,
  "currency_code": "JPY"
}
```

**No tours available:**
```json
{
  "tours": [],
  "count": 0,
  "currency_code": "XYZ",
  "message": "No tours currently available for this currency"
}
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `S3_TOUR_BUCKET` | ✅ | — | S3 bucket name containing tour data |
| `PORT` | | `7000` | HTTP port to listen on |
| `AWS_REGION` | | `ap-southeast-1` | AWS region |
| `S3_TOURS_PREFIX` | | `tours` | S3 prefix for tour JSON files |
| `S3_IMAGES_PREFIX` | | `tours/images` | S3 prefix for tour images |
| `PRESIGNED_URL_EXPIRY_SECONDS` | | `3600` | Pre-signed URL expiry (seconds) |

Copy `.env.example` to `.env` and fill in values for local development.

## Local Development

```bash
pip install -r requirements.txt
S3_TOUR_BUCKET=your-bucket python tour_service.py
```

## Running Tests

```bash
pip install -r requirements.txt pytest
pytest tests/ -v
```

## Docker Build

```bash
docker build -t tour-service:latest .
```

## ECR Push

After `terraform apply` creates the ECR repository (`tour_display_repo`):

```bash
# Set variables
AWS_REGION=ap-southeast-2
AWS_ACCOUNT_ID=<your-account-id>
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/tour_display_repo"
IMAGE_TAG=$(git rev-parse --short HEAD)

# Authenticate Docker to ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Build and push
docker build -t tour-service:${IMAGE_TAG} .
docker tag tour-service:${IMAGE_TAG} ${ECR_REPO}:${IMAGE_TAG}
docker tag tour-service:${IMAGE_TAG} ${ECR_REPO}:latest
docker push ${ECR_REPO}:${IMAGE_TAG}
docker push ${ECR_REPO}:latest
```

## Architecture

- Deployed as ECS Fargate service in **Private Subnet**
- Accessed via ALB at path `/tour_display/*`
- S3 access via **VPC Gateway Endpoint** (no internet egress, no NAT cost)
- IAM Task Role grants `s3:GetObject` and `s3:ListBucket` on the tour bucket only
