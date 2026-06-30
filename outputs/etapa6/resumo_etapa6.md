# Etapa 6 - Projecao de compras para o proximo periodo

## Leitura executiva

A Etapa 6 converte a fila de cobertura da Etapa 4 em uma recomendacao de compra
para 90 dias, mantendo a rede fisica separada da Loja 93/B2B e estimando
investimento apenas quando ha custo valido da Etapa 5.

- Rede completa: 20.324 pares loja x SKU com compra recomendada, somando 1.019.445 unidades de armazenagem.
- Rede fisica sem Loja 93: 20.061 pares recomendados, 993.649 unidades, investimento conhecido de R$ 5,7M.
- Loja 93/B2B: 263 pares recomendados, 25.796 unidades, investimento conhecido de R$ 2,0M.
- Cobertura de custo dos pares recomendados: 9,7% na rede completa. O restante tem quantidade operacional, mas nao tem orcamento estimado.
- Na rede fisica, a categoria com maior volume recomendado e `C - PISOS E REVESTIMENTOS` (264.264 unidades). A loja com maior volume recomendado e a loja 3 (SALVADOR-BA), com 166.885 unidades.
- A fila operacional tem 2.007 pares de prioridade ALTA na rede fisica.

## Principais achados

- O plano e mais operacional do que financeiro: a quantidade recomendada cobre
  todos os pares elegiveis com demanda observada, mas o investimento conhecido
  cobre apenas os itens com custo valido.
- O uso de estoque projetado negativo como zero utilizavel evita inflar compra
  por uma "divida" que pode ser apenas transferencia/ajuste ausente.
- A Loja 93 precisa de rotina propria: a demanda foi recalculada para o canal
  B2B porque a venda media da Etapa 2 era referencia da rede fisica.
- Itens com margem negativa na Etapa 5 permanecem na fila quando ha demanda e
  ruptura, mas a acao recomenda validar preco/margem antes de comprar.

## Limitacoes e riscos de interpretacao

- A quantidade recomendada nao substitui pedido final: faltam saldo fisico atual,
  transferencias, lead time, lote minimo e multiplo de fornecedor.
- O investimento estimado nao e budget total; ele exclui itens sem custo valido.
- A media de meses com venda pode superestimar demanda de itens intermitentes.
- Receita potencial de 90 dias e referencia historica, nao previsao causal.

## Autoaudit / revisao critica

| RISCO | COMO_PODERIA_ERRAR | CONTROLE_APLICADO | EVIDENCIA | RISCO_REMANESCENTE |
| --- | --- | --- | --- | --- |
| Comprar para pares sem demanda observada | Tratar ausencia de venda como zero e ainda assim comprar por status de ruptura inflado. | Quantidade recomendada so e calculada quando existe venda historica do par loja x SKU. | 0 compras recomendadas sem demanda observada. | A demanda historica pode estar subestimada se houve ruptura real prolongada. |
| Orcamento falso para itens sem custo | Multiplicar quantidade por zero ou por custo medio de outro SKU/categoria. | Investimento fica nulo quando o SKU nao tem custo valido na Etapa 5. | 18358 pares recomendados sem custo e 1966 com custo valido. | O plano operacional pode ser maior que o orcamento conhecido. |
| Apagar demanda da Loja 93/B2B | Reusar diretamente a venda media da Etapa 2, que excluiu a Loja 93 da referencia de consumo. | Demanda da Etapa 6 e recalculada a partir das vendas do proprio par, incluindo Loja 93 em escopo separado. | 327 pares da Loja 93 tinham venda observada e venda media Etapa 2 igual a zero; 327 pares da Loja 93 tem demanda propria. | B2B pode ter pedidos grandes e intermitentes; media historica suaviza picos. |
| Interpretar estoque negativo como quantidade a comprar integralmente | Somar o negativo a demanda futura e inflar compras por ausencia de transferencias/ajustes. | Estoque negativo vira zero utilizavel, nao uma divida operacional adicional. | 18453 pares com estoque projetado negativo tratados como zero utilizavel. | Se o negativo refletir venda nao reposta, ainda pode haver subestimativa de necessidade. |

## Validacoes

- 15 validacoes executadas; status geral: `OK`.
- Receita, pares e quantidades reconciliam entre `REDE_COMPLETA`, `REDE_FISICA_SEM_LOJA93` e `LOJA_93_ATACADO_B2B`.
- Receita historica fecha com Etapa 3 e categorias da rede fisica fecham com Etapa 4.
- Investimento nao foi imputado para custo ausente.

## Proximos passos

1. Validar saldo fisico dos itens de prioridade ALTA antes de emitir pedido.
2. Completar custo de SKUs sem custo valido para transformar quantidade em budget.
3. Adicionar lead time, lote minimo e politica de servico por categoria.
4. Rodar sensibilidade de demanda com media de calendario e sazonalidade.
