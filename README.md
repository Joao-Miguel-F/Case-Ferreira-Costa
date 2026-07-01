# Case Técnico — Análise de Desempenho de Produtos no Varejo

Análise completa de 24 meses de dados de uma rede de varejo de materiais de construção com 11 lojas em 5 estados do Nordeste (PE, BA, SE, PB, RN).

---

## Estrutura do repositório

```
.
├── data/
│   ├── raw/                        # Bases originais fornecidas (CSV / XLSX)
│   └── processed/                  # Bases tratadas em Parquet (geradas pelo código)
│
├── notebooks/                      # Análises por etapa
│   ├── 01_etapa1_entendimento_dados.ipynb   # 📘 notebook executado (entregável de leitura)
│   ├── 02_etapa2_estoque_projetado.ipynb    # 📘 notebook executado (com validações antes/depois)
│   ├── 03_etapa3_desempenho_vendas.ipynb    # 📘 notebook executado (rankings, ABC e sazonalidade)
│   ├── 04_etapa4_cobertura_categoria_loja.ipynb # 📘 notebook executado (cobertura por categoria/loja)
│   ├── 05_etapa5_precificacao_margem.ipynb  # 📘 notebook executado (margem, desconto e dispersão de preço)
│   ├── 06_etapa6_projecao_compras.ipynb     # 📘 notebook executado (projeção de compras)
│   ├── etapa1_entendimento_dados.py         # script-fonte de referência
│   ├── etapa2_estoque_projetado.py          # script-fonte de referência (corrigido)
│   ├── etapa3_desempenho_vendas.py          # script-fonte de referência
│   ├── etapa4_cobertura_categoria_loja.py   # script-fonte de referência
│   ├── etapa5_precificacao_margem.py        # script-fonte de referência
│   └── etapa6_projecao_compras.py           # script-fonte de referência
│
├── src/
│   └── utils.py                    # Funções e constantes compartilhadas
│
├── scripts/
│   └── gerar_dashboard.py          # Gera o dashboard HTML a partir dos CSVs reais
│
├── outputs/
│   ├── etapa1/                     # Decisões de tratamento, dicionário de dados
│   ├── etapa2/                     # Cobertura de estoque, investigação de outliers de preço
│   ├── etapa3/                     # Rankings, ABC, categorias, lojas e sazonalidade
│   ├── etapa4/                     # Cobertura por categoria/loja e priorização de reposição
│   ├── etapa5/                     # Margem, preço de lista/desconto, dispersão e candidatos a repricing
│   ├── etapa6/                     # Projeção de compras, priorização e validações
│   └── relatorio_qualidade_dados.html       # 📊 dashboard executivo (abre no navegador)
│
├── requirements.txt
└── README.md
```

---

## Como executar

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Rodar Etapa 1 (limpeza e tratamento — gera os Parquets em data/processed/)
cd notebooks
python etapa1_entendimento_dados.py

# 3. Rodar Etapa 2 (estoque projetado e análise de cobertura — já com as correções)
python etapa2_estoque_projetado.py

# 4. Rodar Etapa 3 (desempenho de vendas, rankings, ABC e sazonalidade)
python etapa3_desempenho_vendas.py

# 5. Rodar Etapa 4 (cobertura por categoria/loja e priorização)
python etapa4_cobertura_categoria_loja.py

# 6. Rodar Etapa 5 (precificação, margem, desconto e dispersão de preço)
python etapa5_precificacao_margem.py

# 7. Rodar Etapa 6 (projeção de compras para 90 dias)
python etapa6_projecao_compras.py

# 8. (opcional) Reexecutar os notebooks de ponta a ponta
jupyter nbconvert --to notebook --execute --inplace 01_etapa1_entendimento_dados.ipynb
jupyter nbconvert --to notebook --execute --inplace 02_etapa2_estoque_projetado.ipynb
jupyter nbconvert --to notebook --execute --inplace 03_etapa3_desempenho_vendas.ipynb
jupyter nbconvert --to notebook --execute --inplace 04_etapa4_cobertura_categoria_loja.ipynb
jupyter nbconvert --to notebook --execute --inplace 05_etapa5_precificacao_margem.ipynb
jupyter nbconvert --to notebook --execute --inplace 06_etapa6_projecao_compras.ipynb

# 9. (opcional) Regenerar o dashboard HTML a partir dos CSVs
cd ..
python scripts/gerar_dashboard.py
```

> **Nota:** os arquivos `data/processed/*.parquet` já estão incluídos no repositório para facilitar a reprodução das análises sem precisar rodar a Etapa 1.

### Abrir os entregáveis de leitura

- **Dashboard executivo:** basta abrir `outputs/relatorio_qualidade_dados.html` no navegador
  (duplo-clique). É autocontido — não precisa de servidor nem instalação. O dashboard consolida
  qualidade de dados, estoque projetado, desempenho de vendas, cobertura por categoria/loja,
  precificação e margem, e recomendações de melhoria. O
  dicionário exibido no dashboard também é salvo em `outputs/dicionario_dados_projeto.csv` e cobre
  bases tratadas e principais outputs analíticos.
- **Notebooks executados:** `notebooks/01_etapa1_entendimento_dados.ipynb`,
  `notebooks/02_etapa2_estoque_projetado.ipynb`,
  `notebooks/03_etapa3_desempenho_vendas.ipynb`,
  `notebooks/04_etapa4_cobertura_categoria_loja.ipynb` e
  `notebooks/05_etapa5_precificacao_margem.ipynb` e
  `notebooks/06_etapa6_projecao_compras.ipynb` já trazem todos os outputs salvos — podem ser
  lidos direto no GitHub, VS Code ou Jupyter, sem rodar nada.

---

## Contexto do negócio

| Dimensão | Dado |
|---|---|
| Período analisado | jan/2024 – dez/2025 (24 meses) |
| Receita total | R$ 482,5M |
| Linhas de venda (proxy de transações) | 1.090.390 |
| SKUs ativos | 2.729 |
| Lojas | 11 (5 estados) |
| Categorias (Nível 1) | 23 |

**Ponto de atenção — Loja 93 (Alhandra-PB):** opera como canal B2B/atacado com receita média por linha de venda ~20× superior à rede e 76% da receita em Eletros. Todas as análises são apresentadas com e sem esta unidade para não distorcer os indicadores da rede física.

---

## Etapas realizadas

### Etapa 1 — Entendimento e Limpeza

- Inspeção de 8 bases (fatos + dimensões)
- 10 decisões de tratamento documentadas com justificativa analítica
- Integridade referencial 100% entre produtos, vendas e lojas
- Hipóteses de negócio levantadas antes das análises formais
- Bases tratadas exportadas em Parquet com colunas derivadas (RECEITA, QTD_ARMAZENAGEM, FLAG_LOJA93)

**Achados principais:**
- 80% da receita (R$385M) vem de SKUs sem compra registrada no período → estoque inicial é o principal ativo operacional
- Loja 93 representa 31,8% da receita com apenas 12% dos SKUs → operação B2B/atacado
- 2.549 SKUs com variação de preço >30% → possível inconsistência de precificação

### Etapa 2 — Estoque Projetado e Cobertura

Metodologia: `Estoque_t = Estoque_inicial + ΣEntradas_até_t - ΣSaídas_até_t`

Todas as quantidades convertidas para **unidade de armazenagem** antes da operação.

Valores **pós-correção** (ver seção [Revisão de qualidade e correções](#revisão-de-qualidade-e-correções)):

| Status | Pares loja×produto | % |
|---|---|---|
| Em ruptura (estoque ≤ 0) | 26.140 | 91,0% |
| Crítico (1–30 dias de cobertura) | 573 | 2,0% |
| Atenção (31–90 dias) | 391 | 1,4% |
| Saudável (>90 dias) | 955 | 3,3% |
| Sem venda (capital imobilizado) | 662 | 2,3% |
| **Total** | **28.721** | **100%** |

**Interpretação:** o alto percentual de ruptura é consistente com a descoberta da Etapa 1 — a rede opera principalmente do estoque inicial, sem reposição registrada em ~88% dos SKUs. Após a correção, o topo do ranking de reposição passou a incluir os pares de maior receita da base (Eletros da loja 93), antes invisíveis. O foco da Etapa 6 (plano de compras) deve priorizar os pares **em ruptura/crítico com maior receita histórica**.

### Etapa 3 — Análise de Desempenho de Vendas

Foram gerados rankings por receita e quantidade em unidade de armazenagem, curva ABC por receita, agregações por hierarquia de produto (`NIVEL_1`, `NIVEL_2`, `NIVEL_3`), loja, cidade/estado e evolução mensal. Todas as saídas têm visão de **rede completa** e **rede física sem Loja 93**.

**Achados principais:**
- Rede completa: R$ 482,5M, 1.090.390 linhas de venda (proxy de transações) e 2.729 SKUs ativos.
- Loja 93: 31,8% da receita e 2,3% das linhas de venda, com receita média de R$ 6.160,07 por linha.
- Rede física sem Loja 93: R$ 329,2M e 1.065.507 linhas de venda.
- Produto líder por receita na rede completa: `467774` — COND.SPLIT 9000 COND.S3UQ09 INV. 143, com R$ 12,5M.
- Produto líder por receita na rede física: `432048` — MASSA CORRIDA PVA CORAL PLS 25KG, com R$ 9,9M.
- Curva A: 522 SKUs concentram 80,0% da receita na rede completa; sem Loja 93, são 713 SKUs.
- A receita caiu 54,2% em 2025 vs 2024 na rede completa e 47,6% na rede física sem Loja 93.
- A maior contribuição bruta para a queda de 2025 veio de `D - ELETROS` e, por loja, da Loja 93.

**Limitações e cuidados:** a análise é descritiva; picos e quedas não são atribuídos a causa sem evidência adicional. `TRANSACOES` representa linhas de venda, não cupons únicos, pois a base não tem id de cupom/pedido/nota. Ticket médio = proxy de receita por linha de venda; preço médio = receita por unidade de armazenagem. A Loja 93 é segregada para evitar mistura entre atacado/B2B e rede física.

**Como executar:**

```bash
cd notebooks
python etapa3_desempenho_vendas.py
```

Arquivos auditáveis em `outputs/etapa3/`, incluindo rankings, curva ABC, desempenho por categorias/lojas, sazonalidade, decomposição da queda, notas metodológicas, recomendações de melhoria e `resumo_etapa3.md`.

### Etapa 4 — Cobertura por Categoria e Loja

A Etapa 4 agrega o snapshot de cobertura da Etapa 2 por `NIVEL_1`, `NIVEL_2`, `NIVEL_3`, loja e categoria×loja, cruzando com os outputs auditáveis da Etapa 3 para priorizar reposição por receita histórica em risco. A Loja 93 é mantida na rede completa, mas a priorização operacional compara a rede física separadamente.

**Achados principais:**
- Rede completa: 28.721 pares loja×produto; 26.713 (93,0%) em ruptura/crítico.
- Receita histórica associada a pares em ruptura/crítico: R$ 464,6M na rede completa e R$ 316,3M na rede física sem Loja 93.
- Categoria com maior receita em risco: `D - ELETROS` (R$ 190,7M na rede completa; R$ 78,8M na rede física).
- Loja física com maior receita em risco: loja 3 (SALVADOR-BA), com R$ 58,7M em ruptura/crítico.
- Maior prioridade categoria×loja na rede física: `D - ELETROS` na loja 92 (CABO DE SANTO AGOSTINHO-PE), com R$ 17,0M de receita em risco.
- Loja 93 é analisada à parte: `D - ELETROS` concentra R$ 111,9M de receita em risco nesse canal.

**Limitações e cuidados:** cobertura continua sendo uma métrica conservadora baseada nos dados disponíveis; não representa disponibilidade física real. `DIAS_COBERTURA` infinito/sem venda é contado separadamente, e médias/medianas usam apenas valores finitos. A ausência de transferências, ajustes de inventário, lead time e política de estoque limita a conversão direta da priorização em quantidade ideal de compra. `TRANSACOES` segue sendo proxy de linhas de venda nos cruzamentos com a Etapa 3.

**Como executar:**

```bash
cd notebooks
python etapa4_cobertura_categoria_loja.py
```

Arquivos auditáveis em `outputs/etapa4/`, incluindo cobertura por categorias/lojas, priorização categoria×loja, recomendações de melhoria, validações, `resumo_etapa4.md` e `documentacao_tecnica_etapa4.md`.

### Etapa 5 — Precificação e Variação de Margem

A Etapa 5 calcula a margem bruta realizada (R$ e %), markup e custo médio por SKU, categoria e loja, sempre na **mesma unidade de armazenagem**, e compara o preço praticado com o preço de lista (`dim_precos`) para medir o desconto efetivo — **dentro da mesma embalagem**. Também mede a dispersão de preço do mesmo SKU entre lojas (por embalagem) e prioriza candidatos a repricing. A Loja 93 (atacado/B2B) é segregada em universo próprio e o custo de cada universo usa apenas as compras das lojas do universo.

**Achados principais:**
- Custo de compra válido existe só para **261 SKUs** (de 2.729 vendidos): **R$ 79,1M, 16,4% da receita** na rede completa (15,2% na rede física). A margem realizada vale apenas para esse subconjunto — análogo ao "88% vendem sem compra registrada" das Etapas 1/2.
- Margem bruta % média ponderada (itens com custo): **47,6% na rede completa** (markup 1,91×) e **49,8% na rede física** (markup 1,99×).
- Maior margem por categoria na rede física (cobertura ≥10%): `C - PISOS E REVESTIMENTOS` (56,1%); menor: `D - ELETROS` (42,8%). `B - UTILIDADES DOMÉSTICAS` aparece com **margem negativa** (−15,4%) no subconjunto com custo — louças/porcelanas de baixo giro vendidas abaixo do custo.
- Desconto efetivo médio ponderado na rede física: **17,4%**; **2.264** combinações loja×produto×embalagem vendem **acima da lista** (desconto negativo → tabela possivelmente desatualizada).
- Dispersão de preço entre lojas (rede física, embalagem 0): apenas **46 SKUs com CV>30%** — bem abaixo da leitura ingênua de "2.549 SKUs com variação >30%", que misturava embalagem e atacado.
- **3.260** candidatos a repricing na rede física (326 de prioridade ALTA), combinando margem baixa/negativa, desconto alto e preço fora da faixa da rede. O sinal de margem é calculado no grão loja×produto×embalagem.

**Revisão de qualidade (autoaudit):** três armadilhas tratadas explicitamente — (1) **margens absurdas por erro de unidade**: preço e custo normalizados para a unidade de armazenagem mantêm todos os 261 markups na faixa sanitária (0,65×–4,76×), prevenindo o falso outlier de "venda em caixa"; (2) **custo de SKU sem compra vazando para a margem**: 2.468 SKUs (R$ 403,4M, 83,6% da receita) ficariam com margem fabricada se o custo fosse imputado — corrigido restringindo a margem aos SKUs com custo próprio; (3) **mistura de embalagem na dispersão**: a leitura ingênua marcava ~2,6k SKUs com variação >30%; separando embalagem e atacado, caem para 46 (pelo CV).

**Limitações e cuidados:**
- Margem realizada existe só para os ~261 SKUs com custo (~16% da receita); o restante fica sem margem por ausência de dado, não por erro.
- O custo é a média ponderada do período, sem camadas de custo (PEPS) nem custo de reposição atual.
- O preço de lista (`dim_precos`) pode não refletir promoções pontuais; o desconto efetivo é uma aproximação.
- A Loja 93 é atacado/B2B: margens não comparáveis ao varejo, por isso segregada em `LOJA_93_ATACADO_B2B` (margem auditável de 43,9% nos SKUs com custo).

**Como executar:**

```bash
cd notebooks
python etapa5_precificacao_margem.py
```

Arquivos auditáveis em `outputs/etapa5/`: `margem_produtos.csv`, `margem_categorias_n1/n2/n3.csv`, `margem_lojas.csv`, `margem_total_universo.csv`, `precificacao_desconto.csv`, `dispersao_preco_lojas.csv`, `candidatos_repricing.csv`, `recomendacoes_melhoria.csv`, `validacoes_etapa5.csv`, `autoaudit_etapa5.csv`, `resumo_etapa5.md` e `documentacao_tecnica_etapa5.md`.

### Etapa 6 — Projeção de Compras para o Próximo Período

A Etapa 6 transforma a cobertura e a priorização das etapas anteriores em um plano operacional de compra para **90 dias**, no grão loja×SKU. A quantidade recomendada usa demanda histórica do próprio par, estoque projetado utilizável e status de cobertura; o investimento financeiro só é estimado quando existe custo válido na Etapa 5. A Loja 93/B2B é tratada em escopo separado — com demanda **e status de cobertura recalculados** a partir das próprias vendas B2B — e os totais fecham em `REDE_COMPLETA`.

**Achados principais:**
- Rede completa: **20.357 pares loja×SKU** com compra recomendada, somando **1.019.914 unidades de armazenagem**.
- Rede física sem Loja 93: **20.061 pares** recomendados, **993.649 unidades**, com **R$ 5,7M** de investimento conhecido.
- Loja 93/B2B: **296 pares** recomendados, **26.265 unidades**, com **R$ 2,1M** de investimento conhecido (a demanda B2B recalculada reclassifica **37 pares** como CRÍTICO/ATENÇÃO que ficariam fora da fila se herdassem o status da Etapa 2).
- Apenas **9,7%** dos pares recomendados têm custo válido; portanto, o plano é mais operacional do que financeiro até completar custos por SKU.
- Categoria com maior volume recomendado na rede física: `C - PISOS E REVESTIMENTOS` (**264.264 unidades**). Loja física com maior volume: loja 3 (SALVADOR-BA), com **166.885 unidades**.
- A fila operacional da rede física tem **2.007 pares de prioridade ALTA**.

**Autoaudit / cuidados críticos:** ausência de demanda observada não vira compra; custo ausente não vira investimento zero; estoque negativo vira zero utilizável, não dívida adicional; e itens com margem negativa exigem validação de preço/margem antes de compra.

**Como executar:**

```bash
cd notebooks
python etapa6_projecao_compras.py
```

Arquivos auditáveis em `outputs/etapa6/`: `plano_compras_sku_loja.csv`, `plano_compras_total_universo.csv`, `plano_compras_categorias_n1.csv`, `plano_compras_lojas.csv`, `priorizacao_compras.csv`, `recomendacoes_melhoria.csv`, `validacoes_etapa6.csv`, `autoaudit_etapa6.csv`, `resumo_etapa6.md` e `documentacao_tecnica_etapa6.md`.

---

## Revisão de qualidade e correções

Uma revisão de qualidade da Etapa 2 identificou **4 problemas**, todos corrigidos em
[`notebooks/etapa2_estoque_projetado.py`](notebooks/etapa2_estoque_projetado.py) e revalidados.
O detalhamento visual (com antes/depois) está no **dashboard**
[`outputs/relatorio_qualidade_dados.html`](outputs/relatorio_qualidade_dados.html) e nos
notebooks executados
[`02_etapa2_estoque_projetado.ipynb`](notebooks/02_etapa2_estoque_projetado.ipynb) e
[`01_etapa1_entendimento_dados.ipynb`](notebooks/01_etapa1_entendimento_dados.ipynb).

| # | Sev. | Problema | Correção | Impacto mensurável |
|---|---|---|---|---|
| **1** | 🔴 Crítico | Receita por par calculada **sem a loja 93** → 263 pares da loja 93 em ruptura ficavam com receita nula e sumiam do ranking | Calcular receita com **todas as lojas** (`excluir_atacado=False`); segregar o atacado só como filtro posterior | **+263 pares** da loja 93 (Eletros de maior receita) reintegrados ao ranking de reposição |
| **2** | 🔴 Crítico | Skeleton montado **só com o estoque inicial**, ignorando pares que vendem sem foto de estoque | Skeleton = **união** de estoque ∪ vendas ∪ compras; sem foto inicial → `ESTOQUE_INICIAL = 0` | **+3.379 pares** incluídos, **+R$ 87,5M** (18,1% da receita) rastreados |
| **3** | 🟠 Médio | `DIAS_COBERTURA` ficava **negativo** (ex.: −566; mín. −720) em rupturas | Piso em 0 quando `ESTOQUE_PROJ ≤ 0` | **14.939 → 0** valores negativos no output |
| **4** | 🟠 Médio | Produto 119959 com preço de R$ 3,68 a R$ 391,55 na mesma loja | Investigado e documentado em [`investigacao_outliers_preco.csv`](outputs/etapa2/investigacao_outliers_preco.csv) | **Não é bug:** venda em caixa (EMBALAGEM=1, CONVERSAO=100) com conversão aplicada. Dos **75** pares com CV>1, **0** são erro de conversão |

**Validações executadas após a correção (no notebook 02):**
- ✅ 263 pares da loja 93 em ruptura agora têm `RECEITA_TOTAL` preenchida (antes: 0)
- ✅ Os 3.379 pares sem estoque inicial agora aparecem na cobertura
- ✅ Nenhum `DIAS_COBERTURA` negativo no output final
- ✅ Resumo antes/depois por `STATUS_ESTOQUE` impresso no notebook e no dashboard

---

## Próximas etapas (planejadas)

- **Etapa 7** — Recomendações finais: promoções, descontinuações, repricing e plano de execução comercial
- **Etapa 8** — Apresentação executiva

---

## Decisões metodológicas

| Decisão | Justificativa |
|---|---|
| Encoding `latin1` em todos os CSVs | Arquivos gerados por sistema legado brasileiro |
| Nulos de estoque → 0 | Conservador: gera alertas precoces de ruptura |
| 132 preços de compra nulos excluídos do CMV | Volume físico válido; custo sem base não pode ser imputado |
| Loja 93 segmentada | Ticket 20× superior, 76% Eletros → operação B2B distorce médias da rede |
| QTD_ARMAZENAGEM = QTD × Conversão | Garantir mesma unidade em saídas, entradas e estoque inicial |
| Estoque negativo = ruptura | Direção conservadora: prioriza reposição dos itens mais vendidos |

---

## Premissas, limitações conhecidas e próximos passos

Decisões assumidas de forma transparente, com os pontos que eu revisitaria antes de tratar os números como definitivos:

- **Velocidade de venda (`VENDA_MEDIA_MES`) é a média dos meses *com* venda, não dos 24 meses.**
  Para itens de venda intermitente isso **superestima a velocidade** mensal e, portanto,
  **subestima os dias de cobertura** — empurrando itens para "Crítico". É uma escolha herdada da
  Etapa 2 original, mantida por consistência; uma variante dividindo o volume total pelos 24 meses
  (ou pelos meses desde a 1ª venda) deve ser comparada na próxima iteração.
- **A ruptura de ~91% não é ruptura física real de 91% da rede.** Ela reflete a *ausência de
  registros de reposição* na base (~88% dos SKUs vendem sem compra registrada — provável reposição
  via transferência entre lojas, não capturada) somada ao tratamento conservador de estoque nulo = 0.
  O indicador serve para **priorização relativa** (o que repor primeiro), não como medida absoluta
  de disponibilidade.
- **Loja 93 (atacado)** entra nos cálculos de receita e estoque (são fatos do par), mas é excluída
  da *referência de consumo da rede física* na cobertura em dias. Isso pode gerar pares da loja 93
  com receita alta e status "Sem Venda" — comportamento esperado, não erro.
- **Queda de 2025 (−54% de receita YoY)** ocorre com os 24 meses presentes (não é gap de dados): o
  volume cai mês a mês ao longo de 2025. Precisa de confirmação de causa (retração de mercado,
  descontinuação de operações ou mudança de captura) — ver aba *Inconsistências* do dashboard.

**Próximos passos sugeridos:** (1) cobertura em dias com média sobre 24 meses + análise de
sensibilidade do status; (2) incorporar transferências entre lojas para fechar o gap dos SKUs sem
compra; (3) decompor a queda de 2025 por categoria e canal (atacado × rede).

---

## Tecnologias

- **Python 3.11+** (testado em 3.14) com pandas, numpy, pyarrow — versões fixadas em `requirements.txt`
- **Parquet** para armazenamento intermediário (5–10× mais rápido que CSV para 1M+ linhas)
- **Chart.js** (via CDN) no dashboard HTML autocontido
- Compatível com Power BI, Tableau e DuckDB para visualização
