# Testes

Suíte única para todo o projeto: **185 testes**, rodados com pytest da raiz do repositório.

```bash
backend/.venv/bin/python -m pytest              # tudo (~25s)
backend/.venv/bin/python -m pytest -m "not lento"   # 162 testes em ~6s
backend/.venv/bin/python -m pytest backend/tests -q # só o backend
```

Com a venv ativada (`source backend/.venv/bin/activate`), basta `pytest`.

A configuração está em [pytest.ini](pytest.ini): ela põe `backend/` e `dataset/` no
`pythonpath`, então `from app import ...` e `import normalizar_dataset` funcionam de
qualquer diretório. Os 20 testes marcados `lento` executam o verificador oficial por
subprocess — cada caso paga um import de pandas, e é daí que vem quase todo o tempo da
suíte.

## O que está coberto

| Arquivo | Testes | Alvo |
|---|---:|---|
| `backend/tests/test_leitor.py` | 41 | `app/data/reader.py`: conversão de tipos |
| `backend/tests/test_repositorio.py` | 25 | `app/data/repository.py`: filtros, ordenação, agregações |
| `backend/tests/test_api.py` | 14 | endpoints sobre o dataset real |
| `backend/tests/test_api_erros.py` | 28 | 400/404/405/500, CORS, bordas de paginação |
| `backend/tests/test_config.py` | 18 | configuração, fábrica, falha por dataset ausente |
| `backend/tests/test_env.py` | 7 | carregamento do `.env` e nomes das chaves |
| `backend/tests/test_contrato_dataset.py` | 12 | contrato entre o backend e os CSVs reais |
| `dataset/tests/test_normalizar_dataset.py` | 20 | normalização, ponta a ponta |
| `dataset/tests/test_verificar_fila_priorizada.py` | 20 | verificador oficial da regra de ouro |

## Convenções

**Dados sintéticos para asserções exatas.** Os testes de unidade montam a própria fila em
`tmp_path` (fixtures `dataset_sintetico` e `mini_dataset`), com três ou quatro linhas sob
controle total. Assim uma asserção pode dizer `== ["SOL-B", "SOL-A", "SOL-C"]` em vez de
"a lista não está vazia".

**Dados reais para contrato.** `test_contrato_dataset.py` e `test_api.py` rodam contra
`dataset/normalizado/` e travam os números conhecidos: 941 solicitações, 1.505 eventos,
177 oncológicas por CID, 44 flags divergentes, 22 pares repetidos, 9 eventos órfãos, 353
esperas acima de 365 dias. Se o normalizador mudar e um desses números sair do lugar, a
suíte quebra — é o ponto.

**Nada escreve no repositório.** Os testes do normalizador redirecionam `BASE` e `OUT` do
módulo para `tmp_path` via monkeypatch, então os CSVs versionados em `dataset/normalizado/`
nunca são sobrescritos ao rodar a suíte.

**O `.env` não é versionado**, então os testes que dependem dele são pulados quando ele não
existe. A conferência de nomes de chave roda sobre o `.env.example`, que é versionado: ela
falha se alguém renomear uma chave em `config.py` e esquecer o arquivo de ambiente — foi
exatamente o risco criado quando `DATA_REFERENCIA` virou `REFERENCE_DATE`.

**O verificador oficial é caixa-preta.** `dataset/verificar_fila_priorizada.py` veio dos
organizadores e não é alterado nem importado: os testes o chamam por subprocess com
`--dataset` apontado para uma fila sintética e conferem código de saída e saída de texto.
Eles documentam a fronteira entre o que ele trata como **erro** (sai com 1: coluna
obrigatória ausente, posição repetida ou não inteira, id inexistente, regra de ouro
violada) e como **aviso** (sai com 0: justificativa vazia, cobertura incompleta,
oncológico fora do arquivo).

## Dependências

`backend/requirements-dev.txt` cobre o backend; os scripts de dataset precisam de pandas,
agora declarado em `dataset/requirements.txt`. A venv em `backend/.venv` tem as duas coisas
e serve a suíte inteira:

```bash
backend/.venv/bin/pip install -r backend/requirements-dev.txt -r dataset/requirements.txt
```

## Um bug que a suíte já pegou

Ao escrever `test_repositorio.py` com dados sintéticos, apareceu que o filtro por
especialidade consultava `especialidade_norm` — coluna que existe em
`procedimentos_normalizados.csv` mas **não** na fila. O filtro só funcionava pelo fallback
em `especialidade`, e o primeiro ramo era código morto. Removido, e
`test_contrato_dataset.py` agora falha se o backend passar a depender de uma coluna que a
fila não tem.

## Idioma

O código do backend é em inglês; os testes seguem em português, e os nomes de colunas do
dataset (`solicitacao_id`, `dias_em_fila`) aparecem como são nos dois lados — eles são o
dado, não identificador nosso.
