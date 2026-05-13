resource "aws_sns_topic" "nmcnpm_system_alert" {
    name = "nmcnpm_system_alert"
    display_name = "NMCNPM System Alerts"
}

resource "aws_sns_topic_subscription" "nmcnpm_system_alert_topic_subcription" {
    topic_arn = aws_sns_topic.nmcnpm_system_alert.arn
    protocol = "email"
    endpoint = "${var.alert_email}"
}