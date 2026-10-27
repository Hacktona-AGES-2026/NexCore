# Análise inicial do desafio e dos dados

## Tema e objetivo

O case da 9ª Hackatona de Engenharia de Software da PUCRS/Fin-x/Hospital São Lucas é **IA para a Jornada Cirúrgica Inteligente no SUS**, com foco em **priorização inteligente da fila cirúrgica**. A questão é quem precisa operar primeiro, por quê e como revisar a decisão conforme a situação muda.

O escopo fixo é produzir uma ordem para a fila completa, com explicações e decisão final de um profissional de saúde. Agenda de salas, preparo pré-operatório e cancelamentos estão fora do escopo. A entrega comum exige `solicitacao_id`, `posicao` e `justificativa` em `fila_priorizada.csv`. A regra de ouro: nenhum caso de neoplasia maligna (CID iniciado por C) pode ficar abaixo de alguém sem urgência clínica. O case não exige ML nem SWALIS; ambos são opcionais. A banca avalia valor ao decisor, originalidade, segurança/explicabilidade e execução técnica.

## Conteúdo do pacote

| Fonte | Registros | Observação |
|---|---:|---|
| `fila_cirurgica.csv` | 941 | Uma linha por solicitação; data de referência 23/10/2026 |
| `eventos_clinicos.csv` | 1.505 | Eventos de espera ligados por solicitação e paciente |
| `procedimentos.csv` | 23 | Catálogo com porte, risco, duração e UTI |
| `referencias/swalis.csv` | 5 classes | Referência opcional, sem mapeamento pronto |

Os dados são explicitamente sintéticos. O pacote inclui dicionário, README e verificador automático da regra de ouro.

## Perfil e problemas encontrados

- 177 solicitações têm CID iniciado por C. A flag manual `flag_oncologico` diverge do CID em 44 linhas; decisões de segurança devem derivar oncologia do CID normalizado.
- 22 solicitações repetem o par paciente/procedimento. São potenciais duplicatas, mas não foram removidas: precisam ser revistas com cautela e decisão explícita.
- Nove eventos apontam para solicitações ausentes da fila atual. Não entram em junções diretas com a fila ativa, mas permanecem no arquivo de eventos.
- Seis eventos têm conteúdo repetido com IDs de evento diferentes. Foram sinalizados; nenhuma linha foi eliminada.
- Não há IDs de solicitação repetidos, nem referências a procedimento ausentes do catálogo. Não foram encontrados pacientes divergentes nos eventos ligados a solicitações ativas.
- A prioridade manual tem variação de caixa, 11 vazios e grafia acentuada em 7 registros (`Média`). É um dado ruidoso, conforme o case.
- Campos ausentes: observações (397), CID secundário (730), distância (20), ASA (26), dor (38), limitação (20), prioridade (11) e HbA1c/data (728 cada). Ausência não significa zero nem ausência de risco.
- 353 pessoas esperam há mais de 365 dias. As datas de entrada são válidas e `dias_em_fila` confere com a data de referência em todas as 941 linhas.
- Eventos mais comuns: contatos telefônicos (425), HbA1c (286), pronto-socorro (203), faltas (189), biópsias (163), imagens (106), reavaliações (92) e internações (41).

## Saída preparada

Os arquivos normalizados estão em `dataset/normalizado/`; o script reproduzível é `dataset/normalizar_dataset.py`. O processamento preserva os CSVs de origem, mantém todas as linhas, uniformiza espaços/Unicode e datas, adiciona chaves CID comparáveis e categorias auxiliares, deriva `oncologico_cid` do diagnóstico e sinaliza eventos duplicados/órfãos. Regras e contagens estão em `dataset/normalizado/analise_qualidade.json`.

Essa etapa prepara uma base consistente para explorar critérios de priorização, comparar prioridades manuais com evidências clínicas e definir como lidar com solicitações possivelmente duplicadas. Ela não escolhe pesos, classes clínicas nem uma solução de produto.
