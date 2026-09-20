# V1.23.0 R2 — promoção resiliente e saúde do worker

## Motivo

Na primeira promoção da V1.23.0, a aplicação e as migrações foram
atualizadas, mas o healthcheck do worker excedeu dez segundos. O processo de
rollback tentou então executar a imagem antiga sobre o banco já migrado e o
proxy continuou apontando para o endereço do contêiner anterior. A aplicação
foi recuperada manualmente sem perda de dados.

## Correções

- pool do worker local e remoto ampliado para quatro conexões, com uma
  conexão excedente controlada;
- healthcheck do worker com prazo de 30 segundos, cinco tentativas e janela
  inicial de 90 segundos;
- validação do commit exato no heartbeat do worker;
- confirmação da promoção local pelo heartbeat fresco gravado no banco,
  iniciado depois do novo contêiner, no commit aprovado e com as lideranças do
  scheduler e do monitor de alertas, sem reprovar o processo por um estado
  Docker transitório;
- reinício do proxy após a recriação do app e validação pública de
  `https://formacaodoinvestidor.com.br/ready`;
- remoção do rollback automático de código antigo depois que o banco pode
  ter recebido migrações novas;
- a imagem anterior continua preservada para uma recuperação manual e
  compatível com o estado do banco;
- o commit do app é registrado depois do `/ready` público e o commit do worker
  em marcador separado, somente depois do heartbeat funcional;
- a atualização de staging também reinicia/valida o proxy e não relança uma
  imagem antiga sobre o banco de teste migrado;
- logs de falha do heartbeat passam a guardar o traceback completo;
- o mesmo endurecimento foi aplicado ao futuro worker da segunda instância.

## Comportamento esperado na promoção

1. backup do banco;
2. recriação e confirmação de saúde do app;
3. reinício do proxy e confirmação pública de `/ready`;
4. ativação do worker local ou remoto;
5. confirmação de heartbeat e das duas lideranças no commit aprovado;
6. gravação separada da confirmação do worker.

Se o worker falhar, a aplicação nova permanece online e o script informa que
não executou downgrade automático. Os trabalhos continuam preservados na fila
do PostgreSQL para retomada posterior.

## Validação

- testes de regressão para pool e tolerância do healthcheck;
- testes para reinício do proxy e validação pública;
- testes para a ordem do marcador final de produção;
- testes que proíbem o downgrade automático inseguro;
- testes do worker remoto e da verificação do commit no heartbeat.
