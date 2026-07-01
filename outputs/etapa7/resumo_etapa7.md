# Etapa 7 - Recomendacoes finais e plano de execucao comercial

## Leitura executiva

A Etapa 7 e a sintese de decisao: consome os artefatos auditaveis das Etapas 3-6
e classifica cada par loja x SKU em uma de quatro acoes comerciais, sem recalcular
base crua. Cada par recebe UMA acao primaria por precedencia
(DESCONTINUAR > PROMOVER > REPRECIFICAR > COMPRAR) para nao dupla contar capital
ou quantidade. Os tres universos ficam segregados e fecham em REDE_COMPLETA.

### Rede fisica sem Loja 93

- **COMPRAR** (REDE_FISICA_SEM_LOJA93): 19.126 pares, valor conhecido R$ 4,6M (cobertura de custo 9,7%).
- **REPRECIFICAR** (REDE_FISICA_SEM_LOJA93): 956 pares, valor conhecido nao aplicavel (cobertura de custo 0,0%).
- **PROMOVER** (REDE_FISICA_SEM_LOJA93): 752 pares, valor conhecido R$ 6,7M (cobertura de custo 24,7%).
- **DESCONTINUAR** (REDE_FISICA_SEM_LOJA93): 434 pares, valor conhecido R$ 0,4M (cobertura de custo 16,8%).

### Loja 93 (atacado/B2B)

- **COMPRAR** (LOJA_93_ATACADO_B2B): 263 pares, valor conhecido R$ 1,3M (cobertura de custo 4,6%).
- **REPRECIFICAR** (LOJA_93_ATACADO_B2B): 33 pares, valor conhecido nao aplicavel (cobertura de custo 0,0%).
- **PROMOVER** (LOJA_93_ATACADO_B2B): 20 pares, valor conhecido R$ 0,0M (cobertura de custo 5,0%).
- **DESCONTINUAR** (LOJA_93_ATACADO_B2B): 29 pares, valor conhecido sem custo (cobertura de custo 0,0%).

### Fila de execucao (prioridade ALTA, rede fisica)

- 2.036 pares de prioridade ALTA na rede fisica, distribuidos por acao: {'COMPRAR': 1913, 'REPRECIFICAR': 96, 'PROMOVER': 19, 'DESCONTINUAR': 8}.

## Principais achados

- O plano e mais operacional do que financeiro: capital imobilizado, valor de
  encalhe e investimento de recompra so sao mensurados no subconjunto com custo
  valido (Etapa 5). Sem custo o par permanece na fila como sinal, mas sem valor.
- O guarda-corpo de descontinuacao protege os campeoes de receita: SKUs curva A
  parados sao roteados para escoar/transferir, nunca para saida do sortimento.
- Repricing separa o que e problema de margem auditavel (35
  pares primarios) do que e sinal de preco/lista: 73
  com custo valido, mas sem margem baixa/negativa, e 881
  sem custo.
- A Loja 93 entra com escopo proprio e status B2B recalculado; nunca se mistura
  as medias do varejo. REDE_COMPLETA e a soma reconciliada dos dois escopos.

## Limitacoes e riscos de interpretacao

- Estoque projetado nao e contagem fisica: descontinuar/promover exige validar
  saldo e obsolescencia antes de agir.
- Giro usa media dos meses com venda; itens sazonais podem parecer parados fora
  de estacao. Cruzar com a sazonalidade da Etapa 3.
- A fila diz o que fazer e em que ordem, nao quanto descontar nem o lote de
  recompra; falta politica comercial por categoria.
- Valor financeiro conhecido nao e budget total; exclui itens sem custo.

## Autoaudit / revisao critica

| RISCO | CONTROLE_APLICADO | EVIDENCIA |
| --- | --- | --- |
| Descontinuar campeao historico so por giro baixo recente | Curva A parado nunca entra em DESCONTINUAR; curva ausente tambem bloqueia descontinue automatico. Ambos sao roteados para PROMOVER/revisao. | 132 pares curva A parados protegidos e roteados para PROMOVER; 3 pares sem curva protegidos; 463 pares (curva B/C conhecida) restam como DESCONTINUAR. |
| Promover/reprecificar item como se a margem fosse conhecida sem evidencia | Repricing separa SINAL_MARGEM_AUDITAVEL (tem custo) de SINAL_PRECO_LISTA (nao exige custo) e nao gera valor financeiro. Promover so estima capital com custo valido. | 35 pares de repricing primario com sinal de margem auditavel; 73 com custo valido mas apenas sinal de preco/lista; 881 sem custo e apenas sinal de preco/lista. |
| Misturar a Loja 93 (atacado/B2B) nas recomendacoes de varejo | Universo operacional segrega a Loja 93; a base herda o status recalculado da Etapa 6 (demanda B2B propria). REDE_COMPLETA e a soma reconciliada. | 345 pares acionaveis sao da Loja 93 e ficam no escopo LOJA_93_ATACADO_B2B, nunca no universo fisico. |
| Dupla contagem de um par que dispara mais de uma acao | Cada par recebe UMA acao primaria por precedencia (DESCONTINUAR > PROMOVER > REPRECIFICAR > COMPRAR); o valor financeiro agregado usa so a acao primaria. Os demais sinais ficam como flags. | 990 pares disparam mais de um sinal; todos entram uma unica vez na fila via acao primaria. |

## Validacoes

- 23/23 validacoes OK; status geral: `OK`.
- Receita da base fecha com a Etapa 3; REDE_COMPLETA = rede fisica + Loja 93 por acao.
- Sinais de COMPRAR e REPRECIFICAR reconciliam com as Etapas 6 e 5.
- Nenhum curva A ou curva ausente foi descontinuado; Loja 93 tem curva de guarda-corpo.
- Pares sem metrica de prioridade ficam em BAIXA; financeiro nunca imputado sem custo.

## Proximos passos

1. Validar saldo fisico e obsolescencia dos itens ALTA de descontinuar/promover.
2. Completar custo por SKU para transformar capital e recompra em valores fechados.
3. Definir profundidade de desconto/elasticidade por categoria para a promocao.
4. Levar a fila priorizada para a apresentacao executiva (Etapa 8).
