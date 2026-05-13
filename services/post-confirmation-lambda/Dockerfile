# Dockerfile — Post-Confirmation Lambda
#
# Sử dụng AWS Lambda Python base image để đảm bảo môi trường khớp với runtime Lambda.
# Build image này và push lên ECR, sau đó cấu hình Lambda dùng container image.
#
# Build:
#   docker build -t post-confirmation-lambda .
#
# Run locally (test):
#   docker run -p 9000:8080 \
#     -e DB_SECRET_ARN=arn:aws:secretsmanager:... \
#     -e DB_HOST=localhost \
#     -e DB_PORT=5432 \
#     -e DB_NAME=nmcnpm \
#     post-confirmation-lambda
#
#   curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
#     -d @test_event.json.

FROM public.ecr.aws/lambda/python:3.12

# Copy requirements và cài dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy handler
COPY handler.py ${LAMBDA_TASK_ROOT}/

# Lambda handler entry point: <module>.<function>
CMD ["handler.handler"]
# CI/CD smoke test marker.
