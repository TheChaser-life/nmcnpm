variable "s3_vpc_gateway_endpoint_id" {
    type = string
}
variable "account_id" {
    type = string 
}

variable "admin_iam_arns" {
    description = "Danh sách ARN của IAM users/roles được phép truy cập S3 từ ngoài VPC (Terraform, CI/CD). Dùng wildcard: arn:aws:iam::ACCOUNT:user/* hoặc ARN cụ thể."
    type        = list(string)
    default     = []
}
