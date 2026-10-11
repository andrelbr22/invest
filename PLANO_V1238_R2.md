# Entrega da V1.23.8 R2

A condição de iniciar a R2 somente depois que a R1 estiver instalada,
homologada e operacional foi cumprida. A confirmação do proprietário ocorreu
com a R1B, e a implementação mantém medições comparáveis antes e depois da
separação do worker.

Escopo comprometido:

1. ativar o worker na segunda VM pela rede privada, mantendo um único banco na
   VM principal, um scheduler e um monitor de alertas;
2. executar e documentar o retorno automático e manual do worker à VM principal;
3. medir consultas PostgreSQL, espera de I/O, pool e índices antes de ajustar
   qualquer parâmetro;
4. criar respostas compactas ou virtualização apenas nos painéis que a
   telemetria da R1 identificar como gargalo;
5. tornar a evidência de navegador obrigatória na promoção depois que a sessão
   automatizada estiver configurada de forma segura.

Os itens de software, validação e documentação estão entregues no pacote R2.
A criação da VM/VNIC/NSG e a execução dos dois ensaios permanecem ações de
infraestrutura deliberadamente separadas, dependentes dos IPs privados reais e
de uma janela aprovada. O código pode ser promovido antes delas com o worker
local, sem alterar o comportamento já homologado.

Não será criado um segundo banco gravável nem serão removidos fallbacks antes
de comprovar cobertura e estabilidade.
