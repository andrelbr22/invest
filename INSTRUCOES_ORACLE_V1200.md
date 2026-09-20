# Implantação da V1.20.0 na Oracle

## Regra

Publicar primeiro em `https://formacaodoinvestidor.com.br/testefdi/`. Não promover para produção sem validação do proprietário.

## Validação

1. Criar backup do banco e confirmar envio ao Object Storage.
2. Atualizar o repositório da homologação.
3. Construir a imagem candidata.
4. Executar a migração Alembic na homologação.
5. Verificar `/testefdi/health` e `/testefdi/ready`.
6. Rodar toda a suíte Pytest.
7. Validar login, pesquisa, filtros, carteira, alertas e backtests existentes.

## Worker

O worker permanece opcional nesta entrega. Depois de homologar a fila, ele pode ser iniciado no host atual com o profile `worker`. Use apenas uma réplica enquanto a aplicação estiver na VM de 1 GB.

Não inicie o worker de produção antes de confirmar as migrações e a memória disponível. A separação para uma segunda instância será feita na V1.20.1.

## Retorno

Se houver regressão, pare o worker, restaure a imagem anterior e mantenha as tabelas novas sem uso. A migração é aditiva; não execute downgrade em produção como primeira opção.
