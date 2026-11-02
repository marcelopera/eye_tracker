# Convenções e cuidados de pesquisa

Este documento reúne orientações da [ficha histórica](arquivo/ficha-tecnica-v1.md) e do [contexto](contexto-projeto.md). São orientações para contratos futuros, não afirmações de que a implementação já cumpre essas propriedades.

## Coordenadas e tempo

Use pixels físicos de tela, origem no canto superior esquerdo, x para a direita e y para baixo; registre a área real de apresentação, barras, recortes e rotação. Considere a imagem de câmera após rotação e sem espelhamento; “olho esquerdo” é o do participante. Preserve a relação entre tempos monotônicos no aparelho e PTS da câmera e do estímulo. Não estime tempo de captura apenas dividindo índice por FPS: a taxa pode variar. Marcadores e logs devem permitir medir erro e deriva de sincronização; o formato e a precisão devem ser validados.

## Câmera e armazenamento

A ficha sugere CameraX, câmera frontal sem áudio, FHD e 30 fps como metas a conferir no aparelho. Disponibilidade, resolução e FPS reais, rotação, exposição e comportamento térmico devem ser medidos; não são garantidos. Uma estimativa inicial da ficha é cerca de 0,1 GB/min em 1080p30, mais derivados; calcule capacidade a partir do bitrate real, duração, retenção e cópias. Proteja disco e cópias e mantenha dados fora do Git.

## Métricas e ética

Separe pontos de calibração e validação. Planeje acurácia como erro angular em validação, precisão como variação durante fixação e perda como percentual de amostras inválidas; documente unidades, distância e critérios de exclusão antes da análise. Nada disso foi validado por uma sessão de teste.

Vídeos de rosto podem conter dados pessoais sensíveis. Antes de coletar dados de outras pessoas, confirme aprovação ética, consentimento, retenção, acesso e descarte com o CEP e a universidade. Guarde a relação entre nome e pseudônimo separadamente e com proteção adequada; não publique vídeos ou dados de participantes. A licença de código não concede direitos sobre dados ou datasets.
