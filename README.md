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
│   ├── etapa1_entendimento_dados.py         # script-fonte de referência
│   └── etapa2_estoque_projetado.py          # script-fonte de referência (corrigido)
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

# 4. (opcional) Reexecutar os notebooks de ponta a ponta
jupyter nbconvert --to notebook --execute --inplace 01_etapa1_entendimento_dados.ipynb
jupyter nbconvert --to notebook --execute --inplace 02_etapa2_estoque_projetado.ipynb

# 5. (opcional) Regenerar o dashboard HTML a partir dos CSVs
cd ..
python scripts/gerar_dashboard.py
```

> **Nota:** os arquivos `data/processed/*.parquet` já estão incluídos no repositório para facilitar a reprodução das análises sem precisar rodar a Etapa 1.

### Abrir os entregáveis de leitura

- **Dashboard executivo:** basta abrir `outputs/relatorio_qualidade_dados.html` no navegador
  (duplo-clique). É autocontido — não precisa de servidor nem instalação.
- **Notebooks executados:** `notebooks/01_etapa1_entendimento_dados.ipynb` e
  `notebooks/02_etapa2_estoque_projetado.ipynb` já trazem todos os outputs salvos — podem ser
  lidos direto no GitHub, VS Code ou Jupyter, sem rodar nada.

---

## Contexto do negócio

| Dimensão | Dado |
|---|---|
| Período analisado | jan/2024 – dez/2025 (24 meses) |
| Receita total | R$ 482,5M |
| Transações | 1.090.390 |
| SKUs ativos | 2.729 |
| Lojas | 11 (5 estados) |
| Categorias (Nível 1) | 23 |

**Ponto de atenção — Loja 93 (Alhandra-PB):** opera como canal B2B/atacado com ticket médio 20× superior à rede e 76% da receita em Eletros. Todas as análises são apresentadas com e sem esta unidade para não distorcer os indicadores da rede física.

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
- Loja 93 representa 31,8% da receita com apenas 12% dos SKUs → operação B2B
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

- **Etapa 3** — Análise de desempenho de vendas: ranking, sazonalidade, curva ABC
- **Etapa 4** — Análise de cobertura por categoria e loja
- **Etapa 5** — Análise de precificação e variação de margem
- **Etapa 6** — Projeção de compras para o próximo período
- **Etapa 7** — Recomendações: promoções, descontinuações, repricing
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
