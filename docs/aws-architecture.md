# AWS architecture (rendered)

Mermaid rendering of [`docs/aws-diagram-spec.md`](aws-diagram-spec.md), which
remains the authoritative written spec for hand-drawing this in DrawIO. Nodes
and edges here are a direct translation of that spec's Components and
Connections tables. Everything is real (backed by `infra/*.tf`) — the
highlighted orange edge isn't hypothetical, it's the one connection with a
known gap (mixed content: HTTPS frontend calling an HTTP-only API).

```mermaid
flowchart LR
  Browser(["Browser"])

  subgraph Edge["Global edge / frontend"]
    R53["Route53 zone\naws_route53_zone.main"]
    ACM["ACM cert (us-east-1)\naws_acm_certificate.frontend"]
    CF["CloudFront distribution\naws_cloudfront_distribution.frontend"]
    S3[("S3 bucket (frontend)\naws_s3_bucket.frontend")]
  end

  subgraph VPC["VPC (aws_vpc.main)"]
    subgraph Public["Public subnets"]
      ALB["Application Load Balancer\naws_lb.main"]
      ECS["ECS Service (backend)\nFargate tasks"]
    end
    subgraph Private["Private subnets"]
      RDS[("RDS Postgres\naws_db_instance.postgres")]
      Redis[("ElastiCache Redis\naws_elasticache_cluster.redis")]
    end
  end

  subgraph ControlPlane["IAM / SSM / Autoscaling"]
    IAMRole["IAM role: ECS task execution"]
    SSM["SSM Parameters (SecureString x4)"]
    AutoScale["Application Auto Scaling\ntarget + CPU/memory policies"]
  end

  subgraph Regional["Regional AWS services"]
    ECR["ECR repository\naws_ecr_repository.backend"]
    CW["CloudWatch Log Group"]
  end

  Browser -->|"HTTPS, static assets\nvia domain_name"| CF
  CF -->|"origin fetch, SigV4-signed via OAC"| S3
  Browser ==>|"REST + WebSocket, http://api.domain_name\ncross-origin, HTTP-only"| ALB
  ALB -->|"HTTP :backend_container_port"| ECS
  ECS -->|":5432"| RDS
  ECS -->|":6379"| Redis
  IAMRole -.->|"ssm:GetParameters + kms:Decrypt"| SSM
  IAMRole -.->|"pulls image"| ECR
  ECS -.->|"writes logs (awslogs)"| CW
  AutoScale -.->|"adjusts desired count"| ECS
  R53 -.->|"alias: domain_name"| CF
  R53 -.->|"alias: api.domain_name"| ALB
  ACM -.->|"TLS cert"| CF

  linkStyle 2 stroke:#e67e22,stroke-width:3px
```
