# Desafio Técnico

## Visão Geral

Bem-vindo(a) ao desafio técnico! O objetivo é avaliar sua capacidade de projetar e implementar uma solução **fullstack completa**, cobrindo **frontend, backend e IAC**, com foco em arquiteturas modernas, escalabilidade e boas práticas de engenharia.

Você deverá construir uma **aplicação de chat multiusuário**, onde:

- Múltiplos usuários podem conversar entre si;
- **Um usuário não pode visualizar a conversa de outro usuário** que não seja com ele (isolamento de conversas/salas);
- A comunicação em tempo real deve ser implementada;
- Deve haver um **endpoint de webhook** exposto para receber eventos externos (ex.: simular integração com um provedor terceiro, como um sistema de notificações ou gateway de mensagens);
- Pontos extras para uso de **WebSocket** e **integração com uma LLM** (OpenAI, Anthropic Claude, Bedrock, modelos locais, etc.).

**Tempo estimado:** este desafio foi desenhado para ser resolvido em um **final de semana** (aproximadamente 8-16h de esforço). Não esperamos uma solução perfeita e 100% "production ready" — priorize demonstrar clareza de arquitetura, boas práticas e decisões técnicas bem justificadas.

---

## Escopo Funcional

### Requisitos obrigatórios


1. **Chat multiusuário**
   - Deve ser possível criar/entrar em conversas (1:1 ou em grupo/sala).
   - Um usuário só deve visualizar as mensagens das conversas das quais participa.
   - Persistência das mensagens (banco de dados à sua escolha).

2. **Comunicação em tempo real**
   - Implementação via **WebSocket** (ex.: API Gateway WebSocket na AWS, Socket.IO, ou similar) para envio/recebimento de mensagens sem necessidade de polling.

3. **Endpoint de Webhook**
   - Exposição de um endpoint HTTP (ex.: `POST /webhook/messages`) capaz de receber eventos externos simulando, por exemplo, uma mensagem enviada por um sistema terceiro, que deve ser propagada para a sala/conversa correta em tempo real.
   - Deve haver alguma forma de validação (assinatura, token, etc.) simulando um cenário real de segurança de webhook.

4. **Infraestrutura como código**
   - Toda a infraestrutura necessária para rodar a aplicação na AWS deve ser provisionada via **Terraform**.
   - Pode ser testada localmente com **LocalStack** ou similar, caso não deseje provisionar recursos reais na AWS (opcional, mas caso utilize AWS real, deixar claro como destruir os recursos ao final — `terraform destroy`). Utilize Docker para subir todas as dependencias necessárias para executar as aplicações localmente.

5. **Documentação**
   - README próprio em cada camada (`frontend/`, `backend/`, `infra/`) explicando como rodar o projeto localmente.
   - Diagrama de arquitetura (pode ser feito em Excalidraw, draw.io, Mermaid, etc.) explicando o fluxo de dados.
   - Se possível, faça um desenho considerando todas as peças de uma Cloud AWS necessárias para executar o sistema. (Utilize por ex. DrawIO.)

### Pontos extras (diferenciais avaliados, não obrigatórios)
1. **Autenticação/Identificação de usuários**
   - Pode ser simplificada (ex.: login apenas com nome/e-mail, JWT simples, ou até um mock de auth), desde que cada usuário tenha uma identidade única na sessão.
- Uso de **WebSocket nativo via AWS API Gateway** (ao invés de apenas Socket.IO/long polling).
- Integração com uma **LLM** para, por exemplo:
  - Um bot/assistente disponível dentro do chat que responde perguntas;
  - Sumarização automática de conversas;
  - Moderação de conteúdo das mensagens.
- Uso de filas (**SQS**) ou **Kafka** para desacoplar o processamento de mensagens (ex.: mensagem recebida → fila → consumer → broadcast via WebSocket).
- Arquitetura de **microsserviços** (separação entre serviço de autenticação, serviço de mensagens, serviço de notificações, etc.).
- Uso de conceitos de **microfrontends** (ex.: módulo de chat separado do módulo de autenticação/dashboard, via Module Federation ou abordagem similar).
- Testes automatizados (unitários e/ou integração) no frontend e backend.
- Pipeline de CI/CD (ex.: GitHub Actions) para lint, testes e build.
- Observabilidade (logs estruturados, métricas, tracing).

---

## Stack Esperada

| Camada             | Tecnologias sugeridas                                                            |
|---------------------|-----------------------------------------------------------------------------------|
| Frontend            | React  |
| Backend             | Python (FastAPI ou Flask), WebSocket (via `websockets`, FastAPI, ou API Gateway) |
| Banco de Dados      | PostgreSQL, DynamoDB, ou outro à sua escolha, com justificativa                  |
| Mensageria          | SQS, Kafka, ou similar (opcional, para pontos extras)                            |
| Infraestrutura      | Terraform                |
| LLM (opcional)      | OpenAI API, Anthropic Claude API, AWS Bedrock, ou modelo open source local        |

> Você pode utilizar sites de geração de mocks (ex.: Mockaroo, JSON Server, MSW) para simular dados ou serviços externos quando fizer sentido — mas espera-se que você **domine e demonstre proficiência** nas técnicas centrais do desafio (microsserviços, webhooks, WebSocket, filas), e não apenas "mocke" a arquitetura inteira.

---

## 📁 Estrutura Esperada do Repositório

```
.
├── README.md
├── frontend/
│   ├── README.md
│   └── ...              # aplicação React
├── backend/
│   ├── README.md
│   └── ...              # serviços Python (podem ser subpastas por microsserviço)
├── infra/
│   ├── README.md
│   └── ...              # código Terraform (módulos, envs, etc.)
└── docs/
    ├── architecture.png (ou .md com diagrama Mermaid)
    └── decisions.md      # ADRs / decisões técnicas relevantes
```

> A estrutura acima é uma sugestão. Caso opte por uma abordagem de monorepo com ferramentas específicas, justifique a escolha no README raiz.

---

## Entrega

1. Faça um fork ou crie um repositório privado, adicionando os avaliadores como colaboradores.
2. Realize commits incrementais e com mensagens claras (evite um único commit gigante) — isso nos ajuda a entender seu processo de raciocínio.
3. Ao finalizar, atualize este README com:
   - Instruções de como rodar o projeto localmente (frontend, backend e infra);
   - Decisões técnicas tomadas e trade-offs considerados;
   - O que você faria diferente com mais tempo.
4. Envie o link do repositório para o time de recrutamento.

---

## Dúvidas

Ambiguidades fazem parte do dia a dia de um(a) engenheiro(a) sênior. Caso encontre pontos não especificados neste desafio, **tome uma decisão razoável, documente sua premissa** e siga em frente. Isso também é parte do que estamos avaliando.

Boa sorte e bom desafio!
