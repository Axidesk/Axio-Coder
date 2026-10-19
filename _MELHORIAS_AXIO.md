# Melhorias do Axio anotadas durante o projeto GAME

Caderno pedido pelo Rodrigo a 2026-10-18. Cada item é atrito real medido nesta pasta,
não ideia de gosto. O Axio também tem o seu próprio registo automático em
`CODER/coder/.axio/melhorias_pendentes.json`; este ficheiro é a versão legível.

## APLICADOS a 2026-10-20 (na pasta do Axio)

- **1** — `tool_executar_processo` cria as pastas de destino de `-o`/`--output`/`>` antes
  de arrancar, e diz quais criou (`tools/process.py:_criar_pastas_de_saida`). Só `-o` e
  redirecionamento; o `2>&1` não é confundido com um ficheiro.
- **3** — a URL passada em `url_especifica` fica registada como navegada mesmo quando a
  extração falha, para o planejador poder citá-la (`tools/web.py`).
- **4** — `tool_buscar_web` corta o menu do GitHub (`Skip to content` … `Repository files
  navigation`) antes de devolver o conteúdo, só quando o bloco passa de 1500 caracteres.
- **9** — o `roteiro` aceita o passo `imprimir [seletor]` e devolve a captura com a resposta.
- **16** — `tool_ver_imagem` aceita vários caminhos (linha ou `;`), com as imagens juntas.
- **20** — `print` sem alvo fotografa a JANELA; a página inteira só com `regiao="pagina"`.
- **21** — `teclar` com `manter=true` deixa a tecla premida e a ação `largar` envia o keyup:
  é o caminho para testar controlo de jogo ou canvas.
- **22** — despertador completo (`tool_agendar_despertar`, `/api/despertador`, faixa na
  barra de status com contagem e botão cancelar, nota no campo de mensagem, sobrevive a
  fechar o Axio).
- **23** — categoria `pagamento` no cofre (Cartões, logo abaixo de Identidade), com o
  número e o CVV mascarados também nos campos de edição.

### Falta ainda

- **6** — avisar quando o documento não está `crossOriginIsolated`. Exige mexer na ponte
  (o `estado` hoje não fala com a página) e provar com uma página que use
  `SharedArrayBuffer`; fica para quando houver esse caso outra vez.
- **2, 5, 7, 8, 10, 12, 13, 14, 15, 17, 18, 19** — continuam em aberto, como estavam.

## 1. `tool_executar_processo` não avisa que a pasta de destino não existe
`curl -o _baixar/arquivo.zip` falhou com `Failed to open the file: No such file or directory`
depois de arrancar o processo, gastando uma chamada inteira. O curl não cria pastas.
**Cura:** ao arrancar um processo, criar as pastas do `cwd` e as pastas dos caminhos de
`-o`/`>` que não existam — ou recusar antes de arrancar, com a mensagem clara.

## 2. Documentação moderna é ilegível para o `tool_buscar_web`
`https://sparkjs.dev/docs/` voltou como ILEGÍVEL (Shiki/JS) e o exemplo de código saiu
duplicado e embaralhado. A página é a fonte OFICIAL da única biblioteca que resolve o
problema. Consequência: tive de ler a API do próprio ficheiro `.js` no disco para saber
o construtor do `SplatMesh`.
**Cura:** quando a página for um site de docs com Shiki/Prism, extrair o `<pre><code>`
do JSON embutido ou do atributo `data-*`, em vez de desistir com ILEGÍVEL.

## 3. `tool_planejar_arquitetura` recusa fonte oficial ilegível
Exige URLs navegadas, mas a doc oficial do Spark é justamente a que não se lê.
**Cura:** aceitar a URL mesmo com extração parcial, desde que o navegador a tenha aberto.

## 4. Repositório grande devolve 30 000 caracteres de menu do GitHub
O README do `GaussianSplats3D` veio precedido de metade da navegação da página.
**Cura:** cortar automaticamente o bloco de navegação (`Skip to content` … `Repository files navigation`)
antes de devolver o conteúdo.

## 5. Nada no Axio isola "o WebGL não desenha nada" de "o objeto não está lá"
Diagnóstico de uma tela preta consumiu ~9 minutos e 25 chamadas, por tentativa e erro:
acrescentar um cubo à cena provou que o renderer funcionava, e o `drawRange` da geometria
provaria tudo à primeira. Falta um `tool_diagnosticar_webgl` no preview que devolva, de uma
vez: canvas e tamanho real, `renderer.info` (calls/triângulos), `drawRange` e contagem de
atributos de cada malha visível, contexto WebGL2 vivo, e quantos objetos passaram o frustum.
**Cura:** essa fotografia num só pedido, em vez de 25.

## 6. O erro que custou a rodada: `sharedMemoryForWorkers` exige COOP/COEP
Um splat de 3,1 milhões de pontos carregava (contagem certa) mas nunca desenhava:
`drawRange.count` ficava a 0 porque o *sort* no worker falhava com `SharedArrayBuffer`
indisponível. Nenhum erro na consola. A cura foi `sharedMemoryForWorkers: false`.
**Cura no Axio:** quando uma biblioteca declara usar `SharedArrayBuffer`, o preview e o
servidor devem dizer logo se o documento está `crossOriginIsolated` — hoje é invisível.

## 7. Falta um medidor de cena 3D local
Depois de baixar um `.ply`/`.splat`, preciso da caixa, do eixo "para cima" e da escala
para a câmara nascer no sítio certo. Hoje isso é um script à mão.
**Cura:** estender `tool_medir_malha` para ler `.splat`/`.spz`/`.ply` de Gaussian Splatting
e devolver caixa, centro e eixo mais longo — a mesma resposta que já dá para `.obj`/`.glb`.

## 8. Não há leitura numérica de uma imagem que EU acabei de gerar
Ao projetar os quadros do vídeo para coordenadas cilíndricas esqueci um fator da focal.
O resultado foi uma imagem de riscas verticais — e o único sinal disso foi o OpenCV achar
`0 keypoints` numa imagem cheia de conteúdo. Um perfil de variância por **linha** teria dito
numa linha "todas as linhas são iguais" e poupado três tentativas de 80 segundos.
**Cura:** `tool_ver_imagem` (ou um `tool_medir_imagem`) devolver, junto da imagem, a variância
por linha e por coluna, o número de linhas/colunas constantes e um aviso quando a variação
num eixo é ~0 — a assinatura de uma projeção colapsada ou invertida.

## 9. `roteiro` não sabe imprimir
Para cada iteração do render eu precisava de três chamadas: `recarregar`, `clicar #btn-entrar`,
`print`. O `roteiro` já junta as duas primeiras — falta o passo de captura.
**Cura:** aceitar `imprimir <seletor>` como passo do `roteiro`, devolvendo a imagem no fim,
para o ciclo editar→ver ser uma chamada em vez de três.

## 10. Nada mede os intrínsecos de um vídeo
Toda a reconstrução depende da focal da câmara, e não há ferramenta que a dê: tive de a
estimar (640 px) a partir do campo de visão típico de um telemóvel, sabendo que uma focal
errada estica a panorâmica inteira. O `ffprobe` não traz o FOV.
**Cura:** `tool_info_video` com resolução, fps real, duração, orientação, bitrate por quadro
(a 120 fps num ficheiro de 10 MB cada quadro tem pouquíssimo bitrate — e isso explica a
suavidade da imagem) e, quando existir, a focal declarada nos metadados.

## 12. Nenhuma ferramenta estima profundidade de uma imagem
Para dar paralaxe à panorâmica precisei de um mapa de profundidade e não existe nada no Axio
que o produza: escrevi a inferência ONNX à mão (`tools/profundidade.py`). O `onnxruntime`
já estava instalado com CUDA e o modelo é pequeno (Depth Anything V2 Small, 24,8 M parâmetros,
99 MB) — faltou só a ferramenta.
**Cura:** `tool_estimar_profundidade` (imagem ou vídeo → mapa de profundidade + preview),
reusando o `onnxruntime` que o OCR já carrega. Cabe na VRAM desta máquina (medido: ~1,5 GB).

## 13. Uma panorâmica precisa de profundidade em cubemap, e o Axio não tem projeção nenhuma
Estimar profundidade no equirectangular inteiro dá resultado suave e errado: o modelo foi
treinado em perspectiva. A diferença medida foi visível — a malha saiu como um manto ondulado.
Passando a estimar nas 6 faces de um cubo e a costurar, a geometria ficou lisa.
Falta: `tool_equirectangular_para_faces` e o caminho de volta, mais o ajuste de escala entre
faces (cada inferência tem escala própria; alinhei-as por mediana contra um mapa global).
**Cura:** essa ida-e-volta como ferramenta, não como código de projeto.

## 14. Não há como inspecionar uma cena three.js por números
Para saber se as riscas verticais vinham da geometria ou da textura gastei 3 prints e um
teste com material magenta (`map = null; color = 0xff00ff`). Com uma ferramenta que
devolvesse o grafo da cena — malhas visíveis, contagem de vértices, `drawRange`, bounding box,
`renderer.info.render` e o estado dos atributos — a resposta era imediata.
**Cura:** `tool_observar_preview(acao='cena3d')` no preview.

## 15. `tool_observar_preview(acao='avaliar')` trava a página e não diz por quê
Um `new Promise` que nunca resolveu bloqueou a linha principal e a ferramenta respondeu
"a página não respondeu em 8 s" sem indicar qual parte do código correu mal. Como o preview
não expõe `THREE` no escopo global, qualquer expressão que o use rebenta sem sinal claro.
**Cura:** (a) `avaliar` com teto de tempo interno e a devolver o último `console.log` antes do
bloqueio; (b) expor as bibliotecas carregadas (`THREE`, etc.) no escopo do preview.

## 16. `tool_ver_imagem` aceita UM ficheiro; `tool_ler_arquivo` aceita vários
Para comparar 3 imagens de diagnóstico (face, profundidade, face vizinha) precisei de uma
chamada por imagem. O `tool_ler_arquivo` já resolve isto com vários caminhos de uma vez.
**Cura:** aceitar vários caminhos em `tool_ver_imagem`, devolvendo todas as imagens juntas.

## Limitação técnica medida (não é do Axio — é do problema)
Uma panorâmica **rotacional** (câmara a girar no mesmo ponto) não contém informação de
profundidade: nenhum objeto se desloca em relação ao outro. Estimar profundidade e projetar
dá uma paralaxe *inventada*. Medido nesta rodada: com 22 cm de deslocamento a cena derrete
(a camisa e a parede esticam como gelatina). Com 0 cm fica perfeita.
Consequência: paralaxe real exige **translação** da câmara e reconstrução verdadeira
(SfM/COLMAP + Gaussian Splatting), não profundidade monocular num panorama.
O `tools/profundidade.py` fica no projeto para quando houver um vídeo que ande de verdade.

## 11. Candidato a ferramenta genérica (ainda vive neste projeto)
`tools/panorama.py` transforma um vídeo de telemóvel numa panorâmica de 360° navegável:
projeção cilíndrica, alinhamento quadro a quadro por ORB, fecho de uma volta, costura com
correção de exposição e preenchimento das bordas sem dados. Serviu aqui, mas não é deste
projeto — qualquer vídeo de qualquer pasta volta a precisar disto. Se passar no segundo uso,
sobe para o Axio como `tool_video_para_panorama`.

## 17. `tool_buscar_web` devolve páginas, não arquivos
Para achar um vídeo de banco de imagens aproveitável, a busca voltou três listagens de site
(30 000 caracteres de menu e miniaturas em base64 cada) e nenhum endereço direto. Tive de
procurar à vista, dentro do despejo de HTML, o link `cdn.pixabay.com/..._large.mp4`.
**Cura:** quando o pedido for buscar mídia, extrair os endereços de arquivo por extensão
(`.mp4`, `.webm`, `.jpg`) do HTML e devolvê-los numa lista curta, com tamanho — em vez de
devolver a página inteira. E um `tool_baixar_arquivo` com progresso, que hoje é `urllib` à mão.

## 18. Servidor estático sem `Range` quebra o vídeo em silêncio — e é o NOSSO servidor
O `SimpleHTTPRequestHandler` do Python **não suporta requisições parciais**. Sem `Range`,
`<video>.currentTime` pode ser aceito e não mover a imagem, sem um único erro na consola:
o sintoma é "o player não busca". Implementei os 206 à mão em `tools/servir.py`.
**Cura:** esse suporte deve ser o padrão de qualquer servidor que o Axio levante para servir
mídia. E o preview devia avisar quando o `Accept-Ranges` não vier na resposta.

## 19. Nada mede o custo de decodificação de um vídeo — e ele decide a jogabilidade
O mesmo vídeo, mesmas imagens, recuava a 2,5 quadros/s ou a 20 quadros/s só pela distância
entre keyframes. Não há ferramenta que diga isso: descobri medindo dentro da página, com
`currentTime` e o evento `seeked`, e depois reencodando com `ffmpeg -g 4` e medindo de novo.
Faltam duas coisas: um `tool_info_video` que leia o GOP médio (`ffprobe -show_frames`) e um
`tool_preparar_video` que produza a versão "de jogar" (keyframe curto, `+faststart`) — este
serve qualquer projeto que ponha vídeo numa interface.

## 20. `tool_observar_preview(print)` fotografa a página inteira, não a janela
Duas vezes a imagem voltou com uma faixa preta à direita e em baixo, do tamanho da área que
passa do viewport (`inset: 0` cobre a janela, a "página" é maior). Confundir isto com um
defeito de layout custa uma rodada.
**Cura:** `print` com região padrão = a janela, e a página inteira só a pedido.

## 21. Nada segura uma tecla: testar controlo de jogo exige `avaliar` com `dispatchEvent`
Um jogo lê a tecla **enquanto está premida** (`keydown` sem `keyup`). O
`tool_operar_preview(acao='teclar')` faz down+up no mesmo gesto, por isso não há como provar
"andar com W" nem medir a velocidade que daí resulta — tive de escrever
`window.dispatchEvent(new KeyboardEvent('keydown', {code:'KeyW'}))`, esperar, ler e só então
enviar o `keyup`, dentro de um `avaliar` com promessa.
**Cura:** `teclar` aceitar `manter=true` (envia `keydown` e devolve), mais uma acção
`largar` (o `keyup`); e um `gestos` que aceite sequências temporizadas
(`descer W; esperar 1000; ler ...; soltar W`), que é o que qualquer teste de controlo pede.

## 22. Não existe forma de o agente se auto-agendar (despertador)
Pedido explícito do Rodrigo a 2026-10-19: quando uma operação longa corre (download de 20 GB,
treino, aluguer de GPU), eu fico preso a sondar o estado em chamadas repetidas — e cada
chamada reenvia o contexto inteiro. Falta uma ferramenta que diga "acorda-me daqui a N
minutos" (ou "acorda-me quando este processo terminar, ou quando este ficheiro aparecer") e
que encerre a rodada A SEGUIR, voltando sozinha no momento programado.
**Cura:** `tool_agendar_despertar(quando|depois_de|quando_processo=pid|quando_ficheiro=...,
nota=...)` que grava a intenção no estado da sessão e faz o agendador do Axio retomar a
tarefa com a nota como primeira mensagem. Vale ouro em qualquer projeto longo, não só neste.
Nota: parcialmente coberto hoje por uma única chamada longa
(`tool_listar_processos(esperar=N)`), que custa UM contexto em vez de N — mas essa espera
morre se a resposta da API expirar, e não sobrevive a fechar o Axio.

## 23. O cofre não tem onde guardar dados de cartão
A 2026-10-19 o Rodrigo pôs o número do cartão no campo `email`, o CVV em `telefone` e a
validade em `documento`, porque o cartão de identidade só tem esses campos. Isso não é
desleixo dele: não existe categoria de pagamento e os campos são fixos por categoria, logo
não há nome para "número", "validade" e "cvv".
**Cura:** uma categoria `pagamento` com os campos `titular`, `numero`, `validade`, `cvv`,
`bandeira` (e opcionalmente `pais`), mascarando o número como os outros segredos. Enquanto
não existir, a solução usada foi criar uma entrada de identidade com campos extra
(`cartao_visa_debito`), que a interface mostra por baixo dos fixos.
