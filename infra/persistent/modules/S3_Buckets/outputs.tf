output "training_data_bucket_name" {
  description = "Tên S3 bucket chứa training data CSV từ Dataset Maker"
  value       = aws_s3_bucket.dataset_bucket.bucket
}

output "model_artifact_bucket_name" {
  description = "Tên S3 bucket lưu model artifacts (output của SageMaker Training Job)"
  value       = aws_s3_bucket.model_artifact_bucket.bucket
}

output "tour_bucket_name" {
  description = "Tên S3 bucket chứa tour data và images từ Tour Producer"
  value       = aws_s3_bucket.tour_bucket.bucket
}
