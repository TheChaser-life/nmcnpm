resource "aws_wafv2_web_acl" "main_waf" {
    scope = "REGIONAL"

    # Hành động mặc định nếu request không vi phạm bất kỳ luật nào ở dưới
    default_action {
      allow {}
    }

    # Cấu hình lưu log/metrics tổng thể cho WAF
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name = "Main_WAF_Metrics"
      sampled_requests_enabled = true
    }

    # Chống XSS, Local File Inclusion (LFI), và Bad Bots
    rule {
      name = "AWS_Managed_Rules_Common_Rule_Set" 
      priority = 1

      override_action {
        none {} # Giữ nguyên hành động chặn của AWS
      }

      statement {
        managed_rule_group_statement {
          name = "AWSManagedRulesCommonRuleSet"
          vendor_name = "AWS"
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name = "AWS_Managed_Rules_Common_Rule_Set_Metrics"
        sampled_requests_enabled = true
      }
    }

    # Chống SQL Injection
    rule {
     name = "AWS_Managed_SQLi_Rules"
     priority = 2

     override_action {
       none {}
     }

     statement {
       managed_rule_group_statement {
         name = "AWSManagedRulesSQLiRuleSet"
         vendor_name = "AWS"
       }
     }

     visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name = "AWS_Managed_Rules_SQLi_Rule_Set_Metrics"
        sampled_requests_enabled = true
     }    
    }

    # Chống DDoS
    rule {
        name = "Rate_limit"
        priority = 3

        action {
          block {}
        }

        statement {
          rate_based_statement {
            limit = 500 # tối đa 500 request / 1 IP / 5 phút
            aggregate_key_type = "IP"
          }
        }

        visibility_config {
          cloudwatch_metrics_enabled = true
          metric_name = "Rate_Limit_Metrics"
          sampled_requests_enabled = true
        }
    }
}

resource "aws_wafv2_web_acl_association" "alb_association" {
    resource_arn = var.alb_arn
    web_acl_arn = aws_wafv2_web_acl.main_waf.arn
}