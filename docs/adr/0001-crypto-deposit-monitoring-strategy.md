# 0001. Estratégia de Monitoramento e Custódia de Depósitos Cripto

- **Status:** accepted
- **Data:** 2026-09-05
- **Decisores:** @ratopythonista, Engenharia Cota Certa

## Contexto e Problema

A plataforma Cota Certa opera com um livro-razão interno denominando saldos de Carteira em Reais (BRL) e necessita receber depósitos externos em criptoativos na rede Polygon PoS (Testnet Amoy - Chain ID 80002).
Precisávamos decidir como estruturar a custódia on-chain, o rastreamento de transações e a conversão de valor sem inflar o escopo da Prova de Conceito (POC), confrontando as garantias do Whitepaper do Ethereum (modelo de contas e chamadas), do Yellow Paper (árvores de recibos e logs) e do padrão ERC-20 (EIP-20).

## Decisão

Adotamos um modelo de custódia direta em **Cofre de Depósito EOA** (sem deploy de smart contracts proprietários na POC) com suporte dual a **POL nativo** e **Mock USDC (ERC-20)**, monitorado por um worker assíncrono em Python (`web3.py`) sob as seguintes regras:

1. **Separação Canônica de Leitura (Whitepaper & Yellow Paper):**
   - **ERC-20 (USDC):** Detecção exclusivamente via `eth_getLogs` filtrando o tópico `Transfer(address,address,uint256)` com o Cofre de Depósito no `topic[2]`. Por especificação do Yellow Paper, logs presentes em recibos decorrem apenas de execuções com sucesso, dispensando leitura transação a transação.
   - **POL Nativo:** Varredura direta de blocos (`full_transactions=True`) com filtragem de `tx.to == VAULT` e verificação mandatória de `receipt.status == 1`.
2. **Restrição Canônica a EOAs para Ativo Nativo:**
   - Transferências de POL nativo devem originar-se obrigatoriamente de Contas Externamente Controladas (EOAs) no nível superior da transação. Chamadas internas (*message calls*) disparadas por contratos inteligentes (ex.: Gnosis Safe, Account Abstraction ERC-4337) não são indexadas via RPC padrão e não serão suportadas na POC.
3. **Segurança de Entrada e Prevenção de Abuso:**
   - **Whitelist Rígida de Tokens:** O worker processa exclusivamente o contrato de Mock USDC oficial da Amoy (`0x41E94Eb019C0762f9Bfcf9Fb1E58725BfB0e7582`), prevenindo ataques de falsificação (*token spoofing*).
   - **Filtro de Valor Zero e Poeira:** Transferências com valor zerado (`raw_amount == 0`) — permitidas formalmente pelo EIP-20 e exploradas em ataques de *address poisoning* — são descartadas sumariamente na decodificação do RPC.
4. **Finalidade e Tolerância a Reorganizações (Re-org Safety):**
   - O worker processa blocos com atraso fixo de 20 blocos (`safe_block = latest - 20`, ~40 segundos de confirmação), persistindo a chave única composta `(tx_hash, log_index)` no PostgreSQL para assegurar estrita idempotência contábil (`log_index = -1` para POL nativo).
5. **Atribuição de Usuário e Reconciliação Administrativa:**
   - Cada usuário vincula previamente seu Endereço Externo (único na base).
   - Transferências recebidas de remetentes desconhecidos são descartadas da memória do worker com emissão de log de advertência (`WARN`), mantendo o cursor de blocos em avanço contínuo.
   - Para recuperar depósitos órfãos comunicados posteriormente pelo usuário, disponibiliza-se um comando CLI de conciliação por hash de transação (`reconcile-deposit`), que reexecuta a validação e o crédito de forma atômica.
6. **Oráculo de Preço Híbrido:**
   - A precificação para crédito em BRL utiliza triangulação: consulta on-chain ao oráculo oficial da Chainlink na Polygon Amoy para o par `POL/USD` (`0x001382149eBa3441043c1c66972b4772963f5D43`) e consulta off-chain via API pública para a taxa de câmbio cambial comercial `USD/BRL`.

## Opções Consideradas

- **Deploy de Smart Contract de Custódia (`DepositVault.sol` com EIP-20 `approve` + `transferFrom`):** Rejeitado para a POC devido ao custo operacional de deploy, auditoria e fricção de UX (exigiria duas transações pelo usuário: aprovação de cota e depósito).
- **Suporte a Tracing RPC (`trace_filter` / `debug_traceBlock`):** Rejeitado por indisponibilidade em nós públicos comunitários gratuitos e custo excessivo em provedores gerenciados.
- **Tabela de Custódia Pendente (Depósitos Órfãos no Banco):** Rejeitado em favor do descarte em memória com ferramenta CLI de conciliação, evitando acúmulo de dados não atribuíveis no banco e vetores de spam.
- **Taxa de Câmbio Fixa Estática:** Rejeitada para garantir fidelidade contábil e mitigar riscos de arbitragem na conversão para BRL.

## Consequências

- **Positivas:** Arquitetura leve, sem custos on-chain de deploy na POC, imune a transações revertidas e tokens falsos, com idempotência garantida e precificação em tempo real.
- **Negativas/Limitações:** Usuários não podem depositar POL via cofres multi-sig (Safe) ou contratos de abstração de conta sem intervenção administrativa; obrigatoriedade de cadastro prévio do Endereço Externo antes de realizar o envio de fundos.
