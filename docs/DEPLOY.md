# Pipeline e deploy na Hostinger

O workflow é `.github/workflows/ci-cd.yml`:

| Quando | O que roda |
|---|---|
| todo push e todo PR | **Testes Go** (`gofmt`, `go vet`, `go test -race`) e **Testes Python** (`pytest` inteiro, da raiz), em paralelo |
| push na `main`, com os dois verdes | **Deploy na Hostinger** pela [action oficial](https://www.hostinger.com/support/?p=5831) `hostinger/deploy-action@v1` |

Um PR nunca faz deploy. Também dá para disparar à mão em *Actions → CI/CD → Run workflow*
(na `main`).

## Secrets do repositório

Em *Settings → Secrets and variables → Actions → Secrets*:

| Secret | O que é |
|---|---|
| `HOSTINGER_API_KEY` | chave da API, gerada no hPanel (seção API) |
| `HOSTINGER_VM_ID` | id da VPS: o número do hostname (`srv123456.hstgr.cloud` → `123456`) |
| `GEMINI_API_KEY` | chave do Google AI Studio para os textos do Neco; vazia, o Neco usa os textos por regras |

Mais nada: o `SECRET_KEY` do Flask é gerado a cada deploy (o app não usa sessão, e o estado
vive em memória), e o repositório privado é baixado com o `GITHUB_TOKEN` automático do job.

## Como o deploy funciona

A action chama a API da Hostinger, que baixa o repositório na VPS e sobe o
`docker-compose.yml` da raiz como o projeto `nexcore`, substituindo o anterior. Sobem os
três serviços: backend (`:5000`), front (`:8080`) e o simulador, que só começa depois do
healthcheck do backend. A VPS precisa do template com Docker da Hostinger.

As variáveis passam para o compose pelo `environment-variables` da action; as que não
forem passadas usam o padrão do compose (`HOSPITAL_ID=hsl`, `CORS_ORIGINS=*`,
`ENTRY_INTERVAL=10s`…). Para mudar uma delas em produção, acrescente a linha
`NOME=valor` no `environment-variables` do job.

## O que observar

- **Cada deploy recria os containers** e a fila volta ao dataset: a auditoria e o que o
  simulador mandou recomeçam (estado só em memória, por decisão do projeto).
- **Pontos não confirmados na documentação da Hostinger**, a conferir no primeiro deploy:
  - se a VPS constrói as imagens a partir dos Dockerfiles (`build:` no compose). Se o log
    acusar imagem inexistente, a saída é publicar as imagens no GitHub Container Registry
    no workflow e usar `image:` num compose de produção;
  - se a VPS baixa o repositório enquanto o job ainda roda: o `GITHUB_TOKEN` expira quando
    o job termina. Se o log acusar falha de autenticação no GitHub, crie um token pessoal
    (só leitura do repositório), salve como secret `PERSONAL_ACCESS_TOKEN` e troque o
    `personal-token` do job por ele.
- **Portas**: se o firewall da Hostinger estiver ligado, libere 8080 (front) e, se quiser
  o backend direto de fora, 5000.
- **Logs**: no hPanel (Docker Manager da VPS) ou por SSH com `docker compose logs -f`.
