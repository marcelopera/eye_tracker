# Eye tracking por vídeo no smartphone

**Meta em 7 dias:** apresentar o sistema, demonstrar uma sessão funcionando e mostrar resultados preliminares. Disponibilidade: 5 horas por dia.

**Celular grava → servidor processa → painel mostra o olhar**

**Para outra IA entender o projeto:** leia o [contexto e fluxo do sistema](docs/contexto-projeto.md).

## Roadmap

| Etapa | Quando | O que fazer | Pronto quando |
| --- | --- | --- | --- |
| ☐ **1. Coletar** | Dias 1–2 | Android grava câmera frontal durante calibração, estímulo e validação, com registros de sincronização. | Vídeo e registros de uma sessão podem ser conferidos no computador. |
| ☐ **2. Enviar** | Dia 3 | Subir o servidor em Docker no Windows. O app recebe o código do experimento, baixa o estímulo e envia a coleta. | Uma sessão chega íntegra ao servidor. |
| ☐ **3. Processar** | Dia 4 | Usar MediaPipe, sincronizar os registros e calcular o olhar no servidor. | A sessão produz coordenadas e medidas de qualidade. |
| ☐ **4. Visualizar** | Dia 5 | Mostrar no painel o estímulo, o olhar estimado e a qualidade. | É possível abrir e inspecionar uma sessão real. |
| ☐ **5. Medir** | Dia 6 | Repetir os testes e organizar erros, falhas e tempo de processamento. | Há uma tabela ou gráfico com resultados reais e limitações. |
| ☐ **6. Apresentar** | Dia 7 | Preparar slides, ensaiar e gravar uma demonstração de reserva. | Apresentação e demonstração estão prontas. |

**Foco agora: etapa 1 — obter uma gravação local utilizável.**

Os dias são uma sequência proposta, não garantia de duração. Marcar uma etapa somente após conferir sua entrega. Ainda não foi verificado aqui se o novo app realiza a coleta.

## Como trabalhar com a IA

Delegar **uma etapa por vez**, usando a coluna “Pronto quando” como critério de conclusão. A IA implementa e verifica o código; você decide o protocolo, testa no celular e confere os resultados. Quando houver dúvida, a IA deve perguntar.

## Escopo desta entrega

- App simples para coleta e envio; processamento no PC Windows, em containers.
- Uma pipeline baseada em MediaPipe. Sem criar ou treinar detector próprio.
- Infraestrutura limitada; escolher os componentes ao iniciar a etapa 2.
- Atualizar os objetivos da proposta durante a semana. A revisão sistemática e o benchmark entre métodos continuam como trabalho do mestrado, sem precisar estar concluídos nesta demonstração.

## Onde trabalhar

| Pasta | Uso |
| --- | --- |
| `apps/android/` | Aplicativo de coleta — projeto existente preservado |
| `apps/web/` | Painel |
| `services/` | API do sistema |
| `ml/` | Processamento com MediaPipe e calibração |
| `infra/` | Docker |
| `docs/` | Material de referência |

As subdivisões serão criadas quando forem necessárias.

Referências: [resumo do reaproveitamento do app](docs/inventario-app.md) · [ficha técnica original](docs/ficha-tecnica-v1.txt).

A ficha original descreve uma arquitetura mais ampla e um detector próprio; este roadmap registra o escopo atual. O repositório anterior em `C:/Users/marce/mestrado/eye tracking` permanece preservado.
