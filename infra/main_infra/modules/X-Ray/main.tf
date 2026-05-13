resource "aws_xray_sampling_rule" "nmcnpm_sampling_rule" {
  rule_name      = "nmcnpm-production-sampling"
  priority       = 1000
  reservoir_size = 1      # số request/giây được trace bất kể rate
  fixed_rate     = 0.05   # 5% các request còn lại
  url_path       = "*"
  host           = "*"
  http_method    = "*"
  service_type   = "*"
  service_name   = "*"
  resource_arn   = "*"
  version        = 1
}

