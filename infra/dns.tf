# Route53 is a global service; kept on the us-east-1 provider alongside ACM (acm.tf) rather
# than duplicating endpoint config onto the default regional provider.

resource "aws_route53_zone" "main" {
  provider = aws.us_east_1

  name = var.domain_name

  tags = {
    Name = "${local.name}-zone"
  }
}

# Backend/API/WS traffic, still HTTP-only behind the ALB — this record gets no TLS of its own
# (see infra/README.md's "Known gap" section). A future ticket adding an ALB HTTPS listener
# would reuse the ACM certificate below.
resource "aws_route53_record" "alb" {
  provider = aws.us_east_1

  zone_id = aws_route53_zone.main.zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# Frontend SPA, served over TLS via CloudFront.
resource "aws_route53_record" "frontend" {
  provider = aws.us_east_1

  zone_id = aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}
