variable "region" {
    type = string
}

variable "private_subnet_ids" {
    type = list(string)
}

variable "lambda_sg_id" {
    type = string
}

variable "rotate_redis_password_lambda_function_name" {
    type = string
}

variable "rotate_redis_password_lambda_function_arn" {
    type = string
}

variable "travelpayouts_api_key" {
    type = string
}

variable "viator_api_key" {
    type = string
}

variable "exchange_rate_api_key" {
    type = string
}

variable "premium_fee" {
    type = string
}

