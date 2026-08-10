# Chat Multiusuário

Aplicação de chat em tempo real, com isolamento de conversas entre usuários, webhook externo autenticado por HMAC e infraestrutura provisionada via Terraform. Documentação da entrega abaixo; detalhes de cada camada nos READMEs próprios.

## Como rodar o projeto localmente

Requisito único: Docker + Docker Compose.

```bash
docker compose up
```

Sobe Postgres, Redis, backend (FastAPI, hot-reload) e frontend (Vite, HMR) juntos:

- Frontend: http://localhost:5173
- Backend: http://localhost:8000 (health check: `curl http://localhost:8000/health`)
- O backend roda as migrations do Alembic automaticamente na subida.

Detalhes de cada camada (rodar sem Docker, variáveis de ambiente, testes, migrations) estão nos READMEs próprios:

- [`frontend/README.md`](frontend/README.md)
- [`backend/README.md`](backend/README.md)
- [`infra/README.md`](infra/README.md) — Terraform para AWS, com instruções para validar/aplicar contra LocalStack (com a ressalva: ECS, ECR, RDS, ElastiCache, ELBv2 e CloudFront são recursos pagos/Pro-tier do LocalStack e falham com `apply` na edição community — ver "Limitação conhecida" nesse README).

Diagramas de arquitetura (fluxo de dados e infraestrutura AWS): [`docs/architecture.md`](docs/architecture.md) e [`docs/aws-architecture.md`](docs/aws-architecture.md) (renderizações Mermaid); o arquivo editável [`docs/aws-architecture.drawio`](docs/aws-architecture.drawio) e o spec que o originou, [`docs/aws-diagram-spec.md`](docs/aws-diagram-spec.md), também estão versionados.

## Decisões técnicas e trade-offs

Decisões com trade-offs reais viraram ADR em [`docs/adr/`](docs/adr/); deferimentos mais leves e escolhas de tooling estão em [`docs/decisions.md`](docs/decisions.md). Resumo das principais:

- [ADR-0001](docs/adr/0001-containerized-websocket-over-api-gateway.md) — WebSocket é servido pelo próprio container do backend, não via AWS API Gateway (evita ter que rastrear connection IDs externamente no orçamento de tempo do desafio).
- [ADR-0002](docs/adr/0002-explicit-idempotent-conversation-creation.md) — criação de conversa é explícita (`POST /conversations`) e idempotente para 1:1, em vez de implícita no envio da primeira mensagem.
- [ADR-0003](docs/adr/0003-redis-pubsub-for-horizontal-scaling.md) — Redis pub/sub para fan-out entre instâncias do backend, já que "escalabilidade" é critério de avaliação explícito do desafio.
- [ADR-0004](docs/adr/0004-jwt-in-localstorage.md) — JWT em `localStorage` em vez de cookie `httpOnly`, trade-off consciente dado o escopo de "auth simplificada".
- [ADR-0005](docs/adr/0005-client-side-hmac-webhook-test-page.md) — a página de teste do webhook assina o HMAC no browser; segredo aceitável de expor só porque é uma ferramenta de teste manual atrás de login.
- `docs/decisions.md` também documenta as escolhas de stack (Vite, TanStack Query, MUI no frontend; SQLAlchemy async + Alembic, `uv`, bcrypt no backend) e a estrutura por camada (`routers/`, `models/`, `schemas/`, `services/`, `core/`) do backend.

## O que eu faria diferente com mais tempo

Lista completa de itens deferidos em [`docs/decisions.md`](docs/decisions.md#deferred) e [`docs/decisions.md`](docs/decisions.md#extras-not-pursued). Os principais:

- **Offline/unread tracking.** Hoje um participante desconectado busca o backlog via REST ao reconectar, sem read receipts ou contagem de não lidas — é a primeira coisa que eu adicionaria, por ser uma feature genuinamente separada (estado próprio, UI, casos de borda).
- **Rodar sem Redis, single-instance.** O fan-out via Redis pub/sub ([ADR-0003](docs/adr/0003-redis-pubsub-for-horizontal-scaling.md)) foi construído agora, e não deferido, porque escalabilidade é critério avaliado — a alternativa mais simples (uma única instância do backend com um registro de conexões em memória, sem Redis) foi discutida e descartada por esse motivo. O design foi validado por leitura/revisão, mas nunca testado de fato com duas ou mais réplicas do backend rodando simultaneamente; com mais tempo, validaria esse comportamento fim a fim antes de confiar nele em produção.
- **Extras não perseguidos:** bot de LLM no chat, microfrontends, WebSocket nativo via AWS API Gateway ([ADR-0001](docs/adr/0001-containerized-websocket-over-api-gateway.md)), filas (SQS/Kafka) para desacoplar o processamento, arquitetura de microsserviços, pipeline de CI/CD e observabilidade (logs estruturados, métricas, tracing). Auth (JWT) e Tests foram os extras priorizados no orçamento de 8-16h; os demais ficam para depois, nessa ordem de prioridade.
- **Gaps de segurança/robustez conhecidos:**
  - Sem proteção contra replay na assinatura do webhook.
  - Sem checagem de que o `conversation_id` do webhook pertence a um participante — o segredo HMAC é a única fronteira de confiança.
  - Sem forma segura de um sistema externo descobrir a qual conversa postar — hoje precisa saber o UUID de antemão.
  - Sem tiebreaker de ordenação de mensagens além de `created_at`.
  - Refresh token sem rotação no uso — fica válido até expirar ou logout explícito.
  - Logout não fecha WebSockets já abertos com o token antigo — token JWT é stateless e não tem revogação server-side.
  - Token de acesso trafega como query param (`?token=`) no handshake WebSocket, não como header — tende a ficar gravado em logs de acesso de proxies/ALB e em histórico do navegador. Não documentado como trade-off em nenhum ADR; a alternativa seria conectar sem token e autenticar pela primeira mensagem do socket.
- **Ordem de participantes não é uma garantia formal.** A resposta de conversas retorna participantes ordenados por `user_id`, mas isso hoje é efeito colateral do plano de execução do Postgres sobre o índice único composto de `conversation_participants` (confirmado ao investigar o RED de um teste no ticket 23), não uma garantia de SQL/SQLAlchemy — um `ORDER BY` explícito seria o fix correto antes de depender disso.
- **Débito de performance e resiliência no backend, ainda não priorizado:**
  - Sem índice em `messages.conversation_id` — `list_messages` e a busca da última mensagem por conversa fazem table scan à medida que o histórico cresce.
  - O índice único de `conversation_participants` (`conversation_id, user_id`) favorece a checagem de membership, não `list_conversations` — que roda a cada carregamento da sidebar e filtra só por `user_id`.
  - Sem rate limiting em `/auth/login`, `/auth/register` e `/webhook/messages`.
  - Sem paginação em nenhuma listagem (`GET /conversations`, `GET /conversations/{id}/messages`, `GET /users`) — todas devolvem o conjunto inteiro.
  - O subscriber Redis (`run_subscriber`) não tem retry nem log se a conexão cair — a entrega em tempo real para silenciosamente até o processo reiniciar.
- **Frontend sem camada de hooks de dados dedicada.** As query keys do TanStack Query são reescritas à mão em cada rota; centralizar isso e gerar o client TypeScript a partir do OpenAPI que o FastAPI já expõe eliminaria uma classe inteira de bugs de drift entre os schemas Pydantic e as interfaces TS mantidas manualmente em `frontend/src/lib/api.ts`.
- **Gaps de infra conhecidos** (ver [`infra/README.md`](infra/README.md)): NAT Gateway não provisionado (custo sem uso real no desenho atual), e o ALB permanece HTTP-only mesmo com o frontend em TLS via CloudFront.
