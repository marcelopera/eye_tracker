# Contexto do projeto para outras IAs

Este texto descreve o comportamento desejado e as decisões atuais. Não significa que todas as funcionalidades já estejam implementadas. Antes de alterar código, confira o estado real do projeto.

## Objetivo

Desenvolver um sistema para estimar **onde uma pessoa está olhando na tela de um smartphone enquanto assiste a um vídeo**, utilizando a câmera frontal do próprio aparelho.

O celular coleta os dados. Um servidor no computador Windows do pesquisador, executado em containers Docker e acessível pela rede local, processa os arquivos. Um painel web permite preparar experimentos e consultar os resultados. Os dados permanecem no ambiente local do laboratório.

## Conceitos que não devem ser confundidos

| Termo | Significado neste projeto |
| --- | --- |
| Experimento | Configuração de uma coleta: vídeo a apresentar e protocolo com alvos, fases e tempos. Pode ter várias sessões. |
| ID/código do experimento | Identificador gerado pelo backend e informado no aplicativo para localizar um experimento. Não é criado pelo celular nem é o nome de um arquivo. |
| Protocolo | Instruções que o aplicativo executa: calibração, estímulo, validação, marcadores e seus parâmetros. |
| Estímulo | O vídeo que o participante assiste na tela. É cadastrado no sistema e baixado pelo aplicativo. |
| Vídeo da câmera | Gravação do rosto feita pela câmera frontal durante a sessão. É produzida pelo aplicativo e enviada ao servidor. **É um arquivo diferente do estímulo.** |
| Participante | Pessoa que realiza a sessão, identificada no sistema por um código pseudônimo. Esse código não é o código do experimento. |
| Sessão | Uma execução do experimento por um participante. O backend fornece seu identificador próprio. Uma repetição da coleta gera outra sessão. |

O termo “ID do experimento” usado na conversa corresponde à identificação que permite ao app buscar o experimento. A ficha prevê um código curto para uso humano e um ID interno. A representação técnica deve ser definida no contrato; não presumir que esses dois valores sejam iguais. Nenhum deles substitui o endereço do servidor ou uma credencial de acesso.

## Fluxo completo esperado

1. **Preparar no sistema.** O pesquisador cadastra um experimento pelo painel, envia o estímulo e define o protocolo. O backend armazena os dados, prepara o vídeo para reprodução e disponibiliza o código do experimento quando estiver pronto.
2. **Identificar no celular.** O pesquisador informa esse código no app. O app consulta o backend e recebe o protocolo, os metadados e o acesso ao vídeo correspondente. Baixa o estímulo para reproduzi-lo localmente e confere sua integridade. Código inexistente ou experimento ainda não pronto deve gerar uma mensagem clara.
3. **Preparar a sessão.** O pesquisador identifica o participante pelo código, registra as informações exigidas pelo protocolo e confere posicionamento, distância e enquadramento. A sessão fica vinculada ao experimento. Digitar o código não equivale, por si só, a iniciar a câmera ou autorizar a coleta.
4. **Coletar.** Após o início da sessão, o app grava continuamente a câmera frontal, sem áudio, enquanto apresenta as fases abaixo. Também salva os registros temporais e a geometria da tela.
5. **Enviar.** Depois da finalização dos arquivos, o app envia a gravação e os metadados vinculados à sessão. Repetir um envio interrompido não deve criar uma nova sessão. O servidor verifica se os arquivos estão completos e íntegros.
6. **Processar no servidor.** A pipeline extrai landmarks com MediaPipe, sincroniza a gravação com o protocolo e o estímulo, ajusta a calibração da sessão, estima o olhar e calcula a qualidade. O processamento acontece após a coleta; não depende de transmitir imagens ao vivo.
7. **Consultar no painel.** O pesquisador acompanha o estado da sessão e visualiza o olhar sobre o estímulo, as métricas e os arquivos de resultado. Upload recebido e processamento concluído são situações diferentes.

## O que acontece durante a coleta

**Marcador A → calibração → descanso → estímulo → validação → marcador B**

- **Marcadores:** sinais visuais conhecidos, registrados no app e identificáveis na gravação, para relacionar os relógios da câmera e da apresentação.
- **Calibração:** o participante olha para alvos em posições conhecidas. O celular apresenta os alvos e registra seus tempos; o servidor usa esses trechos para ajustar a relação entre features dos olhos e posição na tela.
- **Estímulo:** o vídeo do experimento é reproduzido enquanto a câmera continua gravando.
- **Validação:** outros alvos conhecidos permitem medir o erro. Seus dados não devem ser usados no ajuste da calibração.

Sincronizar significa saber **qual conteúdo estava na tela quando cada imagem da câmera foi capturada**. Não basta iniciar câmera e player ao mesmo tempo. É necessário preservar os PTS do vídeo, os tempos de apresentação e os registros dos alvos/marcadores. A geometria deve incluir a área real do vídeo, barras, rotação e coordenadas da tela.

Uma interrupção da captura deve ser registrada como tal; não juntar trechos silenciosamente e tratá-los como sessão contínua válida. A retomada de envio é uma operação diferente.

## Arquivos e responsabilidades

O pacote previsto contém `face.mp4`, `sync.json`, `calib.json`, `device.json` e `manifest.json`. Eles representam, respectivamente, gravação frontal, sincronização, alvos/fases de calibração e validação, dados do aparelho/tela e lista dos arquivos com versões, tamanhos e hashes. Os campos exatos ainda precisam de contrato.

O Android deve ser simples: obter o experimento, conduzir a sessão, gravar, registrar e enviar. **A inferência e o ajuste matemático da calibração ficam no servidor.** Os arquivos são privados ao aplicativo; não devem aparecer na galeria nem entrar em backup automático. Não apagar a coleta só porque o upload terminou: aguardar a confirmação de processamento e integridade prevista no fluxo.

MediaPipe fornece landmarks; a estimativa da posição na tela também exige features e calibração. Começaremos pela adaptação da pipeline já existente no aplicativo anterior. Não será desenvolvido ou treinado um detector próprio.

## Entrega atual e pesquisa

A entrega inicial, planejada para sete dias com cinco horas diárias do pesquisador, inclui apresentação, demonstração limitada funcionando e resultados preliminares de **uma única pipeline**. A arquitetura pode ser reduzida. Não implementar automaticamente todos os serviços, Kafka, Keycloak, S3, heatmaps ou AOIs da ficha original; o recorte ainda deve ser combinado.

A contribuição científica prevista é a revisão sistemática da literatura e o benchmark entre métodos existentes. Esses trabalhos continuam além da demonstração inicial. Não afirmar que uma sessão de teste constitui benchmark concluído ou precisão validada para outros participantes.

## Orientação para executar trabalho

- Trabalhar em `C:/Users/marce/mestrado/projeto` e seguir o roadmap do `README.md`, uma etapa por vez.
- Preservar o repositório anterior em `C:/Users/marce/mestrado/eye tracking`; usá-lo como referência de reaproveitamento.
- O app anterior faz inferência local em imagens amostradas; não possui o gravador contínuo necessário ao novo fluxo. Não presumir que copiar seu controlador de câmera resolve a coleta.
- Preservar o código já existente no novo projeto e verificar seu comportamento antes de modificá-lo.
- Não recriar estrutura extensa de pastas, filas ou tarefas sem pedido.
- **Perguntar ao pesquisador sempre que houver dúvida.** Tecnologias do protótipo, endpoints, formatos de IDs, parâmetros da coleta e critérios científicos ainda não definidos não devem ser inventados.

A ficha técnica original é referência histórica. Em caso de diferença, considerar as decisões atuais: sistema com processamento no servidor, containerização, app simples e nenhuma criação de detector próprio.
