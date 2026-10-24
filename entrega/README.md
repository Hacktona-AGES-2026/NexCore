# Entrega: fila priorizada

| Arquivo | O que é |
|---|---|
| `fila_priorizada.csv` | **Entregável oficial** do desafio: `solicitacao_id`, `posicao`, `justificativa` para as 941 solicitações. |
| `verificacao.txt` | Saída do verificador oficial (`backend/dataset/verificar_fila_priorizada.py`) sobre a fila do Neco. |
| `comparacao/fila_manual_referencia.csv` | Fila de hoje para comparação: prioridade manual da regulação, desempate pelo maior tempo de espera. |
| `comparacao/verificacao_fila_manual.txt` | Verificador oficial rodado sobre a fila manual. |
| `impacto.json` | Dados do painel "Impacto do Neco" no front (`GET /painel/impacto`). |
| `neco.py` | Cálculo do Neco (classe SWALIS adaptada, índice, ordenação, justificativa). Só biblioteca padrão; o backend pode importar. |
| `gerar_entrega.py` | Gera todos os arquivos acima. |

## Resultado atual

| Indicador do verificador | Fila de hoje | Neco |
|---|---|---|
| Regra de ouro | **177 violações** | **OK, 0 violações** |
| Oncológicos no primeiro terço | 53% | 100% |
| Posição mediana dos oncológicos | 287ª | 112ª |
| PS/internação nos últimos 180 dias na primeira metade | 38% | 87% |
| Sem urgência clínica no último terço | 49% | 97% |

Dos 29 casos A1 (câncer com piora recente), 15 estavam com prioridade manual baixa ou vazia; 66 casos sem urgência estavam com prioridade alta.

Todas as 941 solicitações estão no arquivo. Possíveis duplicatas, divergências entre a flag oncológica e o CID e avisos de cirurgia em outro serviço ou desistência não foram removidos: aparecem na justificativa de cada linha para revisão humana.

## Regenerar

O verificador precisa de pandas (`pip install -r backend/dataset/requirements.txt`). Da raiz do repositório:

```bash
python entrega/gerar_entrega.py
```

Com `--front`, também atualiza os dados do mock do front (`frontend/src/mock/`).
