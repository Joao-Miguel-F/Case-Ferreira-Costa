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
├── notebooks/                      # Análises por etapa (scripts Python executáveis)
│   ├── etapa1_entendimento_dados.py
│   └── etapa2_estoque_projetado.py
│
├── src/
│   └── utils.py                    # Funções e constantes compartilhadas
│
├── outputs/
│   ├── etapa1/                     # Decisões de tratamento, dicionário de dados
│   └── etapa2/                     # Cobertura de estoque, rupturas
│
├── docs/                           # Documentação adicional
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

# 3. Rodar Etapa 2 (estoque projetado e análise de cobertura)
python etapa2_estoque_projetado.py
```

> **Nota:** os arquivos `data/processed/*.parquet` já estão incluídos no repositório para facilitar a reprodução das análises sem precisar rodar a Etapa 1.

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

| Status | Pares loja×produto | % |
|---|---|---|
| Em ruptura (estoque ≤ 0) | 22.812 | 90,1% |
| Crítico (1–30 dias de cobertura) | 571 | 2,3% |
| Atenção (31–90 dias) | 388 | 1,5% |
| Saudável (>90 dias) | 909 | 3,6% |
| Sem venda (capital imobilizado) | 650 | 2,6% |

**Interpretação:** o alto percentual de ruptura é consistente com a descoberta da Etapa 1 — a rede opera principalmente do estoque inicial, sem reposição registrada em 88% dos SKUs. O foco da Etapa 6 (plano de compras) deve priorizar os **571 pares em estado crítico com maior receita histórica**.

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

## Tecnologias

- **Python 3.10+** com pandas, numpy, pyarrow
- **Parquet** para armazenamento intermediário (5–10× mais rápido que CSV para 1M+ linhas)
- Compatível com Power BI, Tableau e DuckDB para visualização
