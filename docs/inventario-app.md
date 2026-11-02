# O que aproveitar do app legado

Origem: app legado; URL do repositório e commit ou tag ainda não informados. Inspeção estática em 27/10/2026; sem executar build ou testes nessa inspeção.

| Aproveitar | O que muda |
| --- | --- |
| Player Media3 e apresentação de alvos | O vídeo e o protocolo virão do experimento. |
| Geometria de tela/vídeo e tratamento de PTS | Salvar os tempos e a área exibida durante toda a sessão. |
| Features oculares e calibração existentes | Adaptar para Python no servidor. |
| Testes de geometria, tempos e features | Usar para conferir as adaptações. |

**Implementar:** gravação frontal contínua, sequência de marcadores/calibração/validação, pacote de arquivos, envio e servidor.

O app legado amostra imagens para inferência local; não grava o MP4 contínuo necessário. Seu histórico de tempos é limitado e fica em memória. A calibração atual também depende da inferência no celular.

Ao adaptar, conferir permissão de rede, exclusão de dados dos backups, orientação e interrupções. O manifesto antigo remove INTERNET e habilita backup; não copiar essas configurações como prontas.

Preservar a origem e aproveitar somente o necessário. O projeto Android presente neste repositório não foi modificado pela simplificação.

[Voltar ao roadmap](../README.md)
