resource "aws_alb" "alb" {
    internal = false
    load_balancer_type = "application"
    security_groups = [var.alb_sg_id]
    subnets = [for id in var.public_subnet_ids : id]

    enable_deletion_protection = false
}

resource "aws_alb_target_group" "frontend_tg" {
    port = 3000 # Port mà service đang chạy
    protocol = "HTTP" # Giao thức dùng để route traffic đến target
    vpc_id = var.vpc_id
    target_type = "ip" # Fargate

    health_check {
        path = "/health"
        protocol = "HTTP"
        matcher = "200" # Mã HTTP trả về báo hiệu máy chủ khỏe mạnh
        interval = 60
        timeout = 10
        healthy_threshold = 3 # Kiểm tra thành công 3 lần liên tiếp thì đưa vào hoạt động
        unhealthy_threshold = 3 # Thất bại 3 lần liên tiếp thì rút máy chủ đó ra khỏi Load Balancer
    }
}

resource "aws_alb_listener" "https_listener" {
    count             = var.cert_arn != "" ? 1 : 0
    load_balancer_arn = aws_alb.alb.arn
    port              = 443
    protocol          = "HTTPS"

    ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
    certificate_arn   = var.cert_arn

    default_action {
        type = "forward" # chuyển tiếp đến frontend tg
        target_group_arn = aws_alb_target_group.frontend_tg.arn
    }
}

resource "aws_alb_listener" "http_listener" {
    load_balancer_arn = aws_alb.alb.arn
    port              = 80
    protocol          = "HTTP"

    default_action {
        type = var.cert_arn != "" ? "redirect" : "forward"
        target_group_arn = var.cert_arn == "" ? aws_alb_target_group.frontend_tg.arn : null

        dynamic "redirect" {
            for_each = var.cert_arn != "" ? [1] : []
            content {
                port        = "443"
                protocol    = "HTTPS"
                status_code = "HTTP_301"
            }
        }
    }
}

resource "aws_alb_target_group" "streaming_exchange_rate_tg" {
    port = 4000 # Port mà service đang chạy
    protocol = "HTTP" # Giao thức dùng để route traffic đến target
    vpc_id = var.vpc_id
    target_type = "ip" # Fargate

    stickiness {
      enabled = true
      type = "lb_cookie" # sử dụng cookie có sẵn của alb
      cookie_duration = 3600
    }

    health_check {
        path = "/health"
        protocol = "HTTP"
        matcher = "200" # Mã HTTP trả về báo hiệu máy chủ khỏe mạnh
        interval = 60
        timeout = 10
        healthy_threshold = 3 # Kiểm tra thành công 3 lần liên tiếp thì đưa vào hoạt động
        unhealthy_threshold = 3 # Thất bại 3 lần liên tiếp thì rút máy chủ đó ra khỏi Load Balancer
    }
}

resource "aws_alb_target_group" "update_money_tg" {
    port = 5000 # Port mà service đang chạy
    protocol = "HTTP" # Giao thức dùng để route traffic đến target
    vpc_id = var.vpc_id
    target_type = "ip" # Fargate

    health_check {
        path = "/health"
        protocol = "HTTP"
        matcher = "200" # Mã HTTP trả về báo hiệu máy chủ khỏe mạnh
        interval = 60
        timeout = 10
        healthy_threshold = 3 # Kiểm tra thành công 3 lần liên tiếp thì đưa vào hoạt động
        unhealthy_threshold = 3 # Thất bại 3 lần liên tiếp thì rút máy chủ đó ra khỏi Load Balancer
    }
}

resource "aws_alb_target_group" "forecast_exchange_rate_tg" {
    port = 6000 # Port mà service đang chạy
    protocol = "HTTP" # Giao thức dùng để route traffic đến target
    vpc_id = var.vpc_id
    target_type = "ip" # Fargate

    health_check {
        path = "/health"
        protocol = "HTTP"
        matcher = "200" # Mã HTTP trả về báo hiệu máy chủ khỏe mạnh
        interval = 60
        timeout = 10
        healthy_threshold = 3 # Kiểm tra thành công 3 lần liên tiếp thì đưa vào hoạt động
        unhealthy_threshold = 3 # Thất bại 3 lần liên tiếp thì rút máy chủ đó ra khỏi Load Balancer
    }
}

resource "aws_alb_target_group" "tour_display_tg" {
    port = 7000 # Port mà service đang chạy
    protocol = "HTTP" # Giao thức dùng để route traffic đến target
    vpc_id = var.vpc_id
    target_type = "ip" # Fargate

    health_check {
        path = "/health"
        protocol = "HTTP"
        matcher = "200" # Mã HTTP trả về báo hiệu máy chủ khỏe mạnh
        interval = 60
        timeout = 10
        healthy_threshold = 3 # Kiểm tra thành công 3 lần liên tiếp thì đưa vào hoạt động
        unhealthy_threshold = 3 # Thất bại 3 lần liên tiếp thì rút máy chủ đó ra khỏi Load Balancer
    }
}

resource "aws_alb_listener_rule" "streaming_exchange_rate_route" {
    listener_arn = var.cert_arn != "" ? aws_alb_listener.https_listener[0].arn : aws_alb_listener.http_listener.arn
    priority     = 1

    action {
        type = "forward"
        target_group_arn = aws_alb_target_group.streaming_exchange_rate_tg.arn
    }

    condition {
        path_pattern {
          values = ["/stream/*", "/stream"]
        }
    }   
}

resource "aws_alb_listener_rule" "update_money_route" {
    listener_arn = var.cert_arn != "" ? aws_alb_listener.https_listener[0].arn : aws_alb_listener.http_listener.arn
    priority     = 2

    action {
        type = "forward"
        target_group_arn = aws_alb_target_group.update_money_tg.arn
    }

    condition {
        path_pattern {
          values = ["/exchange", "/topup", "/balance", "/premium/*"]
        }
    }   
}

resource "aws_alb_listener_rule" "forecast_exchange_rate_route" {
    listener_arn = var.cert_arn != "" ? aws_alb_listener.https_listener[0].arn : aws_alb_listener.http_listener.arn
    priority     = 3

    action {
        type = "forward"
        target_group_arn = aws_alb_target_group.forecast_exchange_rate_tg.arn
    }

    condition {
        path_pattern {
          values = ["/forecast/*", "/forecast"]
        }
    }   
}

resource "aws_alb_listener_rule" "tour_display_route" {
    listener_arn = var.cert_arn != "" ? aws_alb_listener.https_listener[0].arn : aws_alb_listener.http_listener.arn
    priority     = 4

    action {
        type = "forward"
        target_group_arn = aws_alb_target_group.tour_display_tg.arn
    }

    condition {
        path_pattern {
          values = ["/tours/*", "/tours"]
        }
    }   
}

