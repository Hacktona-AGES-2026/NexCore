# Dados normalizados

Gerados por `dataset/normalizar_dataset.py`. Os CSVs originais permanecem intactos na pasta pai. Os arquivos gerados mantêm todas as linhas e colunas de origem, acrescentando colunas auxiliares terminadas em `_norm` e flags de qualidade. Valores ausentes não foram imputados; duplicatas e eventos sem solicitação ativa foram sinalizados, não removidos.

## Arquivos

- `fila_cirurgica_normalizada.csv`: CID comparável em `cid_principal_norm` e `cid_secundario_norm`; `oncologico_cid` derivado do prefixo C; categorias padronizadas em colunas auxiliares.
- `eventos_clinicos_normalizados.csv`: tipo/resultado normalizados e indicadores de duplicidade, solicitação ativa e consistência do paciente.
- `procedimentos_normalizados.csv` e `swalis_normalizado.csv`: cópias com colunas categóricas auxiliares.
- `analise_qualidade.json`: contagens do perfil e regras aplicadas.

Para regenerar, na raiz do repositório:

```bash
python dataset/normalizar_dataset.py
```

## Normalizações aplicadas

Espaços externos removidos, texto em Unicode NFC, campos de data em `AAAA-MM-DD`, CID em maiúsculas e sem ponto nas colunas auxiliares. Município, sexo e categorias ganham versões normalizadas sem substituir seus valores originais. A flag oncológica derivada do CID é a referência para a regra de ouro; a flag manual continua disponível para auditoria.
