# Infra

Terraform para os recursos AWS em que esta aplicação roda: ECS/Fargate (backend), RDS Postgres, ElastiCache Redis,
rede (VPC, ALB), CloudFront/S3 (frontend), Route53/ACM (DNS/TLS), Application Auto Scaling, IAM, e
state remoto (S3 + DynamoDB, provisionado separadamente por `infra/bootstrap/`). Um único state, sem módulos —
cada recurso vive em um arquivo `.tf` nomeado a partir do tipo de recurso que provisiona (`network.tf`, `ecs.tf`,
`rds.tf`, `elasticache.tf`, `frontend.tf`, `acm.tf`, `dns.tf`, `autoscaling.tf`).

Segredos (senha do banco, JWT secret, HMAC secret do webhook) são gerados com `random_password` e publicados
no SSM Parameter Store como parâmetros `SecureString`. A task definition do ECS os injeta no container do
backend via `secrets` (`valueFrom` o ARN do parâmetro), então nada sensível fica hardcoded ou passado como
variável de ambiente em texto plano.

**Sumário:** [State remoto](#state-remoto-infrabootstrap) · [Rodando contra o LocalStack](#rodando-contra-o-localstack) · [Limitação conhecida](#limitação-conhecida) · [Lacuna: NAT Gateway](#lacuna-conhecida-nat-gateway) · [Lacuna: ALB HTTP-only](#lacuna-conhecida-alb-permanece-http-only) · [Hospedagem do frontend](#hospedagem-do-frontend) · [Imagem do container](#imagem-do-container) · [Autoscaling](#autoscaling) · [DNS e TLS](#dns-e-tls) · [Validando](#validando)

## State remoto (`infra/bootstrap/`)

O state do `infra/` principal fica no S3 (com locking via DynamoDB) em vez de um `terraform.tfstate` local, para
que mais de uma pessoa possa dar `apply` sem sobrescrever o state umas das outras. O bucket/tabela desse backend
são provisionados por uma configuração Terraform separada e autocontida — `infra/bootstrap/` — que necessariamente
mantém o *próprio* state local, já que ela cria o backend do qual o `infra/` principal depende.

Rode isso uma vez (por ambiente):

```bash
cd infra/bootstrap
terraform init
terraform apply
```

Isso cria um bucket S3 versionado (`<project>-<environment>-terraform-state`) e uma tabela DynamoDB
(`<project>-<environment>-terraform-lock`) — `chat-app-local-*` com as variáveis padrão.

Depois aponte o `infra/` principal para esse backend:

```bash
cd infra
cp backend.hcl.example backend.hcl   # no .gitignore; edite se você customizou project/environment acima
terraform init -backend-config=backend.hcl
```

`provider.tf` declara um bloco `backend "s3" {}` vazio — um bloco de backend estático não pode referenciar
variáveis, e o bucket/tabela não existem antes do `bootstrap/` rodar, então o bucket/key/region/table reais
são passados via `-backend-config` em vez de hardcoded.

**O que isso prova e o que não prova:** a execução contra o LocalStack abaixo (container único, operador único) confirma
o *mecanismo* do backend S3 — init, leitura/escrita de state e locking via DynamoDB funcionam de ponta a ponta. Não
exercita applies concorrentes de duas pessoas diferentes, já que esse cenário precisa de uma conta AWS real
compartilhada para de fato disparar contenção de lock.

## Rodando contra o LocalStack

Requer o [LocalStack](https://docs.localstack.cloud/) rodando localmente (o tier community/gratuito é suficiente
para dar `apply` em pouco menos da metade deste Terraform — ver "Limitação conhecida" abaixo para saber exatamente
quais recursos).

```bash
# sobe o LocalStack — fixado numa tag community que funciona; a tag `latest` hoje
# exige um LOCALSTACK_AUTH_TOKEN só pra subir, mesmo pras features do free-tier
docker run -d --name localstack -p 4566:4566 localstack/localstack:3.8

# a partir de infra/bootstrap/, uma vez
terraform init
terraform apply

# a partir de infra/
cp backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

O provider `aws` já vem pré-configurado (`provider.tf`) com credenciais fake e todo endpoint apontado para
`http://localhost:4566`, então não precisa de credenciais ou conta AWS. Não precisa do wrapper `tflocal`. Tanto
o provider padrão quanto o alias `aws.us_east_1` (usado por ACM/Route53 — ver "DNS e TLS" abaixo) setam
`s3_use_path_style = true`; sem isso, a criação de bucket S3 contra o LocalStack trava tentando repetidamente
uma requisição `HEAD /` malformada em vez de dar erro, já que o edge router do LocalStack não resolve subdomínios
virtual-hosted-style de bucket (`<bucket>.localhost:4566`) do jeito que o S3 real resolve.

Para derrubar tudo:

```bash
terraform destroy                              # a partir de infra/
cd bootstrap && terraform destroy              # a partir de infra/bootstrap/, por último (o bucket S3
                                                # versionado precisa ter as versões de objeto apagadas
                                                # primeiro, se ainda guardar state)
```

## Limitação conhecida

Confirmado rodando de fato `terraform apply` contra o LocalStack community edition 3.8.1 (ticket 11,
reconfirmado no ticket 25 com os recursos adicionados abaixo): vários serviços usados aqui são exclusivos do
tier Pro do LocalStack e falham com erro 501 "not yet implemented or pro feature" no `apply`, mesmo passando
em `terraform validate`/`plan`:

- **ECS** — `aws_ecs_cluster`, `aws_ecs_service` (`ecs.tf`)
- **ECR** — `aws_ecr_repository` (`ecs.tf`)
- **RDS** — `aws_db_subnet_group`, `aws_db_instance` (`rds.tf`)
- **ElastiCache** — `aws_elasticache_cluster` (`elasticache.tf`, ver ADR-0003)
- **ELBv2** — `aws_lb`, `aws_lb_target_group` (`network.tf`)
- **CloudFront** — `aws_cloudfront_origin_access_control`, `aws_cloudfront_distribution` (`frontend.tf`,
  achado novo do ticket 25)

**Não bloqueados**, ao contrário do que se assumia entrando no ticket 25 — estes aplicaram com sucesso no
tier community: S3 (`aws_s3_bucket.frontend` e afins), Route53 (`aws_route53_zone`, records) e ACM
(`aws_acm_certificate`, `aws_acm_certificate_validation`, incluindo o round-trip de validação via DNS).

**Não testado** — `aws_appautoscaling_target`/`aws_appautoscaling_policy` (`autoscaling.tf`) dependem de
`aws_ecs_service.backend`, que nunca chega a ser criado (ECS é bloqueado no Pro-tier, acima), então o suporte
do Application Auto Scaling no LocalStack não pôde ser exercitado de fato; `terraform plan` é a única evidência
de que está corretamente conectado.

Só VPC/rede (subnets, route tables, security groups, IGW), IAM, CloudWatch Logs, SSM Parameter Store, S3,
Route53 e ACM aplicam com sucesso no tier community. O teste *da aplicação* localmente usa os containers
Postgres/Redis simples do `backend/docker-compose.yml` em vez disso, independente deste Terraform.

## Lacuna conhecida: NAT Gateway

Não provisionado. Um NAT Gateway custa ~US$32+/mês parado, e nada nesse stack usaria a rota privada
hoje — RDS/ElastiCache não precisam de egress para a internet, e o ECS ainda roda nas subnets públicas
(desenho do ticket 02, inalterado aqui). Provisionar um NAT órfão agora seria custo sem retorno. Ele
vem junto com um futuro ticket de "mover ECS para subnets privadas", não antes dele — é esse ticket que
justifica o custo.

**Nota adicional:** o ECS roda com `assign_public_ip = true` — as tasks ficam diretamente acessíveis pela internet, protegidas apenas por security groups (sem egress privado via NAT como alternativa).

## Lacuna conhecida: ALB permanece HTTP-only

`dns.tf` dá ao frontend TLS via CloudFront (`aliases`/`viewer_certificate` apoiados no certificado ACM em
`acm.tf`), mas o ALB em si não recebe mudança de listener/certificado — `api.<var.domain_name>` resolve
para ele só por HTTP puro. Ou seja, `<var.domain_name>` (o frontend) é TLS ponta a ponta, mas o caminho
da API/WebSocket atrás de `api.<var.domain_name>` não é. Adicionar um listener HTTPS ao ALB reaproveitaria
o mesmo certificado ACM; deliberadamente fora de escopo aqui já que o ticket 25 era sobre fechar as lacunas
de hospedagem do frontend/autoscaling/DNS/state, não a segurança de transporte do ALB.

## Hospedagem do frontend

`frontend.tf` provisiona um bucket S3 privado (sem acesso público) mais uma distribuição CloudFront lendo
dele via Origin Access Control — o bucket em si é inacessível exceto pelo CloudFront. Dois blocos
`custom_error_response` transformam 403/404 do S3 (qualquer caminho que não seja um objeto literal, ex.
`/conversations/123`) em um 200 servindo `/index.html`, para as rotas client-side do React Router
funcionarem em carregamento direto e refresh.

Build e deploy:

```bash
./infra/scripts/deploy-frontend.sh
# ou, contra o LocalStack:
LOCALSTACK_ENDPOINT=http://localhost:4566 ./infra/scripts/deploy-frontend.sh
```

Isso roda `npm run build` em `frontend/`, sincroniza `frontend/dist/` com o bucket (`aws s3 sync --delete`),
e (só em AWS real — o LocalStack community não suporta CloudFront, conforme a lacuna acima) invalida o
cache do CloudFront.

## Imagem do container

`backend/Dockerfile` builda o backend FastAPI (multi-stage, dependências gerenciadas por `uv`, roda como
usuário não-root, `uvicorn app.main:app` na porta 8000). Build e push para `aws_ecr_repository.backend`:

```bash
./infra/scripts/push-backend-image.sh
# ou, contra o LocalStack:
LOCALSTACK_ENDPOINT=http://localhost:4566 ./infra/scripts/push-backend-image.sh
```

Marca a imagem com `git rev-parse --short HEAD` (não `latest`) para que os deploys sejam reproduzíveis e
reversíveis — redeploy de um build específico com `terraform apply -var="image_tag=<sha>"`. `var.image_tag`
ainda tem `latest` como *default* por conveniência (primeiro `apply` antes de existir qualquer imagem), mas
o caminho de push documentado sempre usa o SHA do commit.

## Autoscaling

`autoscaling.tf` adiciona um `aws_appautoscaling_target` para `aws_ecs_service.backend` (`min_capacity = 1`,
`max_capacity = 3`) com duas políticas de target-tracking — `ECSServiceAverageCPUUtilization` e
`ECSServiceAverageMemoryUtilization`, ambas mirando 70%. `var.backend_desired_count` ainda define a
contagem *inicial* de tasks do serviço no momento do `apply`; o autoscaling assume o ajuste depois disso.
`aws_ecs_service.backend` tem `lifecycle { ignore_changes = [desired_count] }` (`ecs.tf`) para que um
`terraform apply` posterior não zere de volta uma contagem de tasks já escalada para `var.backend_desired_count`.

## DNS e TLS

`dns.tf` cria uma `aws_route53_zone` para `var.domain_name` (default placeholder: `chat-app.example.com`)
com dois registros alias: o apex (`var.domain_name`) para o CloudFront (frontend, TLS), e
`api.var.domain_name` para o ALB (backend, HTTP-only — ver a lacuna conhecida acima). `acm.tf` solicita o
certificado ACM que o CloudFront precisa para o domínio customizado, especificamente em `us-east-1`
(exigência rígida do CloudFront independente de `var.aws_region`, via o alias de provider `aws.us_east_1`
em `provider.tf`), e o valida via registros DNS nessa mesma zona.

Ir para produção contra a AWS real precisa adicionalmente de: `var.domain_name` apontando para um domínio
de fato registrado, e o registrador desse domínio apontado para o output `route53_name_servers` da zona
(o Terraform não consegue fazer esse último passo — é no registrador, fora da AWS).

## Validando

```bash
terraform validate   # infra/
terraform validate   # infra/bootstrap/
```

Checa só sintaxe e consistência interna — não precisa do LocalStack rodando.
