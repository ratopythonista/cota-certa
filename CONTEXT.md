# Cota Certa

Plataforma de mercado de predição P2P baseada em probabilidades de eventos reais, com cotas binárias precificadas por Formador de Mercado Automatizado (AMM).

## Language

**Market (Mercado)**:
Uma proposição sobre um evento do mundo real com critérios claros de resolução e data de encerramento.
_Avoid_: Evento, aposta, jogo, partida.

**Outcome (Desfecho)**:
Um dos resultados mutuamente exclusivos de um Mercado (especificamente Sim / Não em mercados binários).
_Avoid_: Opção, escolha, palpite.

**Share (Cota)**:
Ativo condicional que paga R$ 1,00 se o Desfecho correspondente ocorrer e R$ 0,00 caso contrário, precificado entre R$ 0,01 e R$ 0,99 conforme a probabilidade implícita de mercado.
_Avoid_: Bilhete, ficha, aposta.

**AMM (Automated Market Maker)**:
O algoritmo matemático de produto constante ($x \times y = k$) que custodia reservas de cotas, precifica compras/vendas e garante liquidez imediata.
_Avoid_: Banca, casa, bookmaker.

**Liquidity Pool (Pool de Liquidez)**:
A reserva de capital e cotas alocada em um AMM para viabilizar as negociações de um Mercado.
_Avoid_: Pote, cofre, banca.

**Resolution (Resolução)**:
O ato oficial de validação do resultado de um evento real por um Oráculo, disparando a liquidação financeira das Cotas.
_Avoid_: Pagamento, premiação, finalização.

**Oracle (Oráculo)**:
A entidade designada (nesta POC, o Administrador) responsável por atestar o resultado do evento e acionar a Resolução.
_Avoid_: Juiz, árbitro.

**Wallet (Carteira)**:
O livro-razão que registra o saldo disponível em Reais do usuário autenticado, depósitos pendentes (Pix/Cripto) e custódia de Cotas.
_Avoid_: Conta, perfil, extrato.
