# Instruções Oracle — V1.23.6 R2D

Publique o ZIP R2D em uma pasta limpa. O novo commit permite que o atualizador
refaça o banco isolado do staging e aplique a 0031 com o identificador
compatível.

Resultado esperado do atualizador:

`Migração aplicada e verificada: 0031_v123_latest_snapshot_idx`

Depois, confirme `/testefdi/ready`, os quatro índices válidos, o ciclo com uma
tentativa por lote, a cobertura integral, a suíte oficial e o benchmark. Não
promova antes da homologação completa e de nova aprovação manual.
