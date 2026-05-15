resource "aws_cognito_user_pool" "nmcnpm_user_pool" {
    name = "nmcnpm_user_pool"

    username_attributes      = ["email"]
    auto_verified_attributes = ["email"]

    verification_message_template {
        default_email_option = "CONFIRM_WITH_CODE"
        email_message        = "Ma xac thuc cua ban la {####}. Vui long nhap ma nay de hoan tat dang ky."
        email_subject        = "Ma xac thuc tai khoan Currency Exchange"
    }

    password_policy {
        minimum_length    = 8
        require_lowercase = true
        require_numbers   = true
        require_symbols   = true
        require_uppercase = true
    }

    schema {
        name                = "premium"
        attribute_data_type = "String"
        mutable             = true
        required            = false

        string_attribute_constraints {
            min_length = 1
            max_length = 5
        }
    }

    lambda_config {
        post_confirmation = var.post_confirmation_function_arn
    }
}

resource "aws_cognito_user_pool_client" "nmcnpm_frontend_client" {
  name            = "nmcnpm_frontend_client"
  user_pool_id    = aws_cognito_user_pool.nmcnpm_user_pool.id
  read_attributes = ["email", "email_verified", "custom:premium"]
}