# ── Stage 1: Builder ─────────────────────────────────────────────────────────
# Install Python dependencies in a separate stage to leverage Docker layer caching
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy only requirements first to leverage Docker cache.
COPY requirements.txt .

# Install dependencies to /usr/local (default pip install location)
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # SageMaker uses this env var to identify the training script
    SAGEMAKER_PROGRAM=train.py \
    # SageMaker standard environment variables (overridden at runtime)
    SM_MODEL_DIR=/opt/ml/model \
    SM_CHANNEL_TRAINING=/opt/ml/input/data/training \
    SM_OUTPUT_DATA_DIR=/opt/ml/output/data

# Create non-root user for security
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 --no-create-home appuser

# Copy installed Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# ── SageMaker BYO Container Directory Structure ───────────────────────────────
# SageMaker expects:
#   /opt/program/train  — executable called to start training
#   /opt/program/serve  — executable called to start inference server
#   /opt/ml/            — runtime data directories (created at job start)

# Create the program directory for SageMaker entry points
RUN mkdir -p /opt/program

# Copy training and inference scripts to /opt/program
COPY train.py /opt/program/train.py
COPY inference.py /opt/program/serve.py

# Create 'train' executable: SageMaker calls this to start a training job
RUN printf '#!/bin/bash\nexec python /opt/program/train.py "$@"\n' > /opt/program/train && \
    chmod +x /opt/program/train

# Create 'serve' executable: SageMaker calls this to start the inference server
# Runs the Flask inference server directly via Python
RUN printf '#!/bin/bash\nexec python /opt/program/serve.py "$@"\n' > /opt/program/serve && \
    chmod +x /opt/program/serve

# Dispatch SageMaker's train/serve command. If SageMaker starts the container
# without an explicit command, infer hosting from existing model artifacts.
RUN printf '#!/bin/bash\nset -e\ncase "${1:-}" in\n  train)\n    shift\n    exec /opt/program/train "$@"\n    ;;\n  serve)\n    shift\n    exec /opt/program/serve "$@"\n    ;;\n  "")\n    if ls /opt/ml/model/*_model.json >/dev/null 2>&1; then\n      exec /opt/program/serve\n    fi\n    exec /opt/program/train\n    ;;\n  *)\n    exec "$@"\n    ;;\nesac\n' > /opt/program/entrypoint && \
    chmod +x /opt/program/entrypoint

# Create SageMaker expected directories
RUN mkdir -p \
        /opt/ml/input/data/training \
        /opt/ml/input/config \
        /opt/ml/model \
        /opt/ml/output/data \
        /opt/ml/output && \
    chown -R appuser:appgroup /opt/ml /opt/program

# Add /opt/program to PATH so SageMaker can find 'train' and 'serve'
ENV PATH="/opt/program:${PATH}"

# SageMaker mounts /opt/ml runtime directories during training. Those mounts can
# be root-owned, so the training process must keep root privileges to write model
# artifacts and failure files reliably.

# Expose port 8080 for inference serving (SageMaker BYO container convention)
EXPOSE 8080

# SageMaker starts training with "train" and hosting with "serve".
ENTRYPOINT ["/opt/program/entrypoint"]
