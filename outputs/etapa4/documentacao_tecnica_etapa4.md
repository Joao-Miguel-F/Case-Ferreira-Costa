# Documentação técnica - Etapa 4

Guia de reprodução e continuação da análise de cobertura por categoria e loja.

## O que foi implementado

A Etapa 4 agrega o snapshot de cobertura da Etapa 2 (`data/processed/cobertura_estoque.parquet` e `outputs/etapa2/cobertura_estoque.csv`) por categoria, loja e categoria × loja. O script canônico é `notebooks/etapa4_cobertura_categoria_loja.py`.

## Como interpretar a cobertura (contexto obrigatório)

- A cobertura (dias de estoque) = `estoque projetado ÷ venda média mensal × 30`.
- O **estoque projetado não é contagem física**: é reconstruído na Etapa 2 como `estoque inicial + compras − vendas` na janela jan/2024–dez/2025.
- A base não tem foto de estoque de abertura para a maioria dos pares (entram com inicial = 0) e ~88% dos SKUs vendem sem compra registrada. Por isso o estoque projetado fica ≤ 0 em ~91% dos pares, que viram "EM RUPTURA".
- Logo, a taxa de ruptura é **conservadora por construção** (erra para sinalizar ruptura a mais, nunca a menos) e mede **prioridade relativa de reposição**, não disponibilidade física real. "Receita em risco" = receita histórica já realizada pelos pares hoje em ruptura/crítico, usada para ordenar prioridade — não é perda projetada.

## Entradas usadas

- `data/processed/cobertura_estoque.parquet`: grão loja × produto com estoque projetado, venda média, dias de cobertura, status e receita histórica do par.
- `outputs/etapa2/cobertura_estoque.csv`: usado nas validações de reconciliação com a Etapa 2.
- `data/processed/dim_produto_tratada.parquet`: adiciona `NIVEL_2` e `NIVEL_3`.
- `data/processed/dim_lojas.parquet`: fallback de cidade/estado.
- `data/processed/vendas_tratadas.parquet`: validação do total de receita, via loader `load_vendas(excluir_atacado=False)`.
- `outputs/etapa3/desempenho_categorias_n1.csv`, `desempenho_categorias_n2.csv`, `desempenho_categorias_n3.csv` e `desempenho_lojas.csv`: cruzamento com receita/participação/variação já auditados na Etapa 3.

## Principais fórmulas

- Receita histórica em ruptura/crítico: soma de `RECEITA_TOTAL` dos pares com `STATUS_ESTOQUE` em `EM RUPTURA` ou `CRÍTICO`.
- Percentual de pares em ruptura/crítico: `PARES_RUPTURA_CRITICO / PARES_LOJA_PRODUTO`.
- Participação da receita em risco no grupo: `RECEITA_RUPTURA_CRITICO / RECEITA_HISTORICA_TOTAL`.
- Participação da receita em risco no universo: `RECEITA_RUPTURA_CRITICO / receita_total_do_universo`.
- Estatísticas de dias de cobertura: média, mediana, p25 e p75 calculados somente sobre `DIAS_COBERTURA` finito. Pares infinitos (sem venda) são contados em `PARES_DIAS_COBERTURA_INFINITO`.

## Separação da Loja 93

Os outputs agregados trazem `UNIVERSO` com `REDE_COMPLETA` e `REDE_FISICA_SEM_LOJA93`. A priorização operacional evita duplicidade: compara lojas físicas apenas no escopo `REDE_FISICA_SEM_LOJA93` e lista a Loja 93 no escopo separado `LOJA_93_ATACADO_B2B`.

## Arquivos gerados

- `cobertura_categorias_n1.csv`: cobertura agregada por `NIVEL_1`.
- `cobertura_categorias_n2.csv`: cobertura agregada por `NIVEL_1` + `NIVEL_2`.
- `cobertura_categorias_n3.csv`: cobertura agregada por `NIVEL_1` + `NIVEL_2` + `NIVEL_3`.
- `cobertura_lojas.csv`: cobertura por loja, cidade, estado e tipo de operação.
- `cobertura_categoria_loja.csv`: cobertura por `NIVEL_1` × loja.
- `priorizacao_reposicao_categoria_loja.csv`: ranking operacional por receita histórica em risco, sem misturar Loja 93 com rede física.
- `recomendacoes_melhoria.csv`: melhorias de dados/modelagem/processo.
- `validacoes_etapa4.csv`: reconciliações numéricas.
- `resumo_etapa4.md`: resumo executivo e metodológico.

## Como revisar ou continuar

1. Rode `cd notebooks && python etapa4_cobertura_categoria_loja.py`.
2. Confira `outputs/etapa4/validacoes_etapa4.csv`; qualquer `FALHA` deve bloquear conclusões.
3. Se alterar a Etapa 2, verifique se `STATUS_ESTOQUE`, `RECEITA_TOTAL` e `DIAS_COBERTURA` mantêm a semântica esperada.
4. Se alterar a Etapa 3, reexecute a Etapa 4 para atualizar cruzamentos de receita/participação.
5. Reexecute `python scripts/gerar_dashboard.py` para atualizar dashboard e dicionário consolidado.

## Limitações que não foram resolvidas aqui

- Sem transferências/ajustes/inventário, a cobertura segue conservadora (superestima ruptura).
- Sem lead time, lote mínimo e política de serviço, a Etapa 4 prioriza urgência relativa, mas não calcula a quantidade ideal de compra.
- Sem id de cupom/pedido/nota, `TRANSACOES` continua sendo linhas de venda.
- A Loja 93 precisa de uma dimensão formal de canal para substituir a regra por código da loja.
