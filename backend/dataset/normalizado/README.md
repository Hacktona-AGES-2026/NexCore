# Dados normalizados

Gerados por `dataset/normalizar_dataset.py`. Os CSVs originais permanecem intactos na pasta pai. Os arquivos gerados mantêm todas as linhas e colunas clínicas de origem, acrescentando colunas auxiliares terminadas em `_norm` e flags de qualidade. Valores clínicos ausentes não foram imputados. Somente as camadas social e geográfica do indicador híbrido `S` possuem fallback neutro explícito `0,5`. Duplicatas e eventos sem solicitação ativa foram sinalizados, não removidos.

## Arquivos

- `fila_cirurgica_normalizada.csv`: CID comparável em `cid_principal_norm` e `cid_secundario_norm`; `oncologico_cid` derivado do prefixo C; categorias padronizadas em colunas auxiliares.
- `eventos_clinicos_normalizados.csv`: tipo/resultado normalizados e indicadores de duplicidade, solicitação ativa e consistência do paciente.
- `procedimentos_normalizados.csv` e `swalis_normalizado.csv`: cópias com colunas categóricas auxiliares.
- `socioeconomic_normalized.csv`: referência municipal com média do INSE por `id_municipio` e inversão min-max em `s_vulnerabilidade` (o fallback `s_ibge`).
- `fila_cirurgica_normalizada.csv`: além dos campos originais, recebe `s_evfam`, `s_ibge`, `s_social`, `s_social_source`, `s_geografico`, as flags de fallback e o `s_vulnerabilidade` final, calculado como `clip(0,8*s_social + 0,2*s_geografico, 0, 1)`.
- As quatro colunas EVFAM-BR são sintéticas nesta base de homologação, possuem
  valores `0/1` reproduzíveis e são identificadas por
  `evfam_dados_sinteticos=sim` e `evfam_sintese_versao=correlated-inse-v1`.
- `disease_burden_normalized.csv`: contrato ainda vazio para `disability_weight`; não confundir peso de incapacidade 0–1 com DALY (`YLL + YLD`).
- `analise_qualidade.json`: contagens do perfil e regras aplicadas.

Para regenerar, na raiz do repositório:

```bash
python dataset/normalizar_dataset.py
```

## Normalizações aplicadas

Espaços externos removidos, texto em Unicode NFC, campos de data em `AAAA-MM-DD`, CID em maiúsculas e sem ponto nas colunas auxiliares. Município, sexo e categorias ganham versões normalizadas sem substituir seus valores originais. A flag oncológica derivada do CID é a referência para a regra de ouro; a flag manual continua disponível para auditoria.
