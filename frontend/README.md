# Frontend

SPA em React (Vite + TypeScript) do chat-app.

## Stack

- Vite + React + TypeScript
- TanStack Query para estado de servidor
- React Router para roteamento (a conversa ativa vive na URL, sem store global)

Veja `docs/decisions.md` na raiz do repositório para o raciocínio por trás dessas escolhas.

## Rodando localmente

**Com Docker (recomendado):**

Na raiz do repositório: `docker compose up`

Isso builda e sobe o frontend (com HMR) junto com backend, Postgres e Redis. O frontend serve em `http://localhost:5173`.

Editar qualquer arquivo em `src/` é refletido imediatamente via HMR do Vite — sem rebuild, sem restart. Adicionar uma nova dependência em `package.json` exige limpar o volume `node_modules` antes de rebuildar, já que o Docker só popula um volume nomeado a partir da imagem uma vez — `docker compose down -v` e depois `docker compose up --build` (ou `docker volume rm <project>_frontend_node_modules` antes de rebuildar).

**Sem Docker:**

1. Copie o arquivo de env e ajuste se precisar: `cp .env.example .env`
2. Instale as dependências: `npm install`
3. Rode o dev server: `npm run dev`

O dev server roda em `http://localhost:5173`.

## Variáveis de ambiente

- `VITE_API_URL` — URL base da API do backend.
- `VITE_WEBHOOK_TEST_SECRET` — precisa bater com o `WEBHOOK_HMAC_SECRET` do backend para a página de teste `/webhook` (ver `docs/adr/0005-client-side-hmac-webhook-test-page.md` na raiz do repositório) assinar as requisições corretamente. Uso exclusivo da página de teste: esse segredo vai junto no bundle do frontend, então nunca configure com um segredo real de produção. Não commite um valor real aqui — `.env` está no `.gitignore`.

## Build

```bash
npm run build
```

Faz type-check com `tsc -b` e gera um bundle de produção em `dist/`.

## Comportamentos conhecidos

- **Mensagens de webhook agrupadas por `source_label`.** Quando `sender_id` é nulo (mensagem trazida por `POST /webhook/messages`), a lista de mensagens agrupa bolhas consecutivas por `source_label` em vez de `sender_id` — sem isso, mensagens de remetentes externos diferentes apareciam sob uma única bolha.
- **Fallback explícito enquanto a identidade do usuário carrega.** A tela de conversa depende de duas queries assíncronas (usuário atual + lista de conversas); antes de ambas resolverem, o nome do participante mostrado usa um fallback explícito de "identidade ainda não conhecida" em vez de arriscar mostrar o participante errado.

## Débito técnico conhecido

- **Sem camada de hooks de dados dedicada.** `useQuery`/`useMutation` são chamados soltos em cada rota (`src/routes/`), cada uma reescrevendo a query key na mão (`['conversations']`, `['messages', conversationId]`, `['me']`, `['users']`). Um typo numa key quebra a invalidação de cache silenciosamente, sem checagem do compilador — centralizar isso em algo como `src/lib/queries/` fecharia essa lacuna.
- **Contrato de API mantido à mão.** As interfaces TypeScript em `src/lib/api.ts` são reescritas manualmente a partir dos schemas Pydantic do backend, sem geração automática a partir do OpenAPI que o FastAPI já expõe. Uma mudança de schema no backend não quebra o build do frontend — só quebra em runtime, silenciosamente.

## Testes

```bash
npm run test
```

Roda a suíte de Vitest + React Testing Library.

**Lacuna conhecida:** o drawer mobile da lista de conversas (`ConversasLayout`) não tem cobertura de teste automatizada própria — verificação manual apenas, por decisão explícita ao escopo daquele ticket.
