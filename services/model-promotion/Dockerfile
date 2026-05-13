# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

# ── Stage 2: Runtime (Lambda base image alternative: dùng slim + manual handler) ──
# Lambda container image yêu cầu dùng AWS Lambda base image để có Lambda Runtime Interface
FROM public.ecr.aws/lambda/python:3.11

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy installed packages từ builder
COPY --from=builder /usr/local/lib/python3.11/site-packages ${LAMBDA_TASK_ROOT}

# Copy source code vào LAMBDA_TASK_ROOT (mặc định /var/task)
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

# Lambda handler: <tên_file>.<tên_hàm>
CMD ["lambda_function.lambda_handler"]
