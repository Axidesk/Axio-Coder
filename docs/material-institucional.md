# Material institucional do Axio Coder

Capturas e gravações da interface do Axio Coder, guardadas fora do repositório por causa do tamanho. O código do projeto vive em `../../coder`.

As descrições de cada vídeo foram confirmadas por um fotograma tirado a 60% da duração — não pelo nome do ficheiro.

## Vídeos

| Ficheiro | Duração | Tamanho | O que mostra |
|---|---|---|---|
| `refatorando modulo js com 5k de linhas.mp4` | 2,0 min | 103,3 MB | O Monaco com um módulo grande aberto, o log da sessão e o painel das ferramentas usadas a listar as chamadas da refatoração |
| `refatorando v2.mp4` | 3,3 min | 166,7 MB | O relatório final da divisão do `renderer.js`: 24 funções para um ficheiro, 26 para outro, com os imports reconferidos |
| `interagindo com preview.mp4` | 7,0 min | 152,2 MB | O preview embutido a servir uma página local e o agente a operá-la, com o editor ao lado |
| `visualizadores de ifc etc.mp4` | 0,9 min | 31,0 MB | O visualizador com abas: IFC, DXF, XLSX, DOCX, PPTX e PNG, cada um no seu leitor |
| `foguete paint.mp4` | 2,3 min | 56,6 MB | O agente a desenhar um foguete no Paint por coordenadas, através da camada de acessibilidade |
| `mexendo no paint.mp4` | 1,3 min | 26,5 MB | Círculo e traços desenhados no Paint, com o raciocínio a explicar as armadilhas encontradas |
| `criando desenho gimp.mp4` | 1,9 min | 65,2 MB | A montagem de uma cena no GIMP por script, com o agente a ler a imagem de volta para conferir |

Total: cerca de 598 MB.

## Capturas

O conjunto de setembro/2026 substituiu as capturas antigas: as que mostravam a interface anterior saíram do repositório.

| Ficheiro | O que mostra | Usada no README do projeto como |
|---|---|---|
| `historico.jpg` | O histórico das sessões com o diff lado a lado e o log em baixo | `historico.jpg` (capa) |
| `plano.jpg` | O plano da tarefa em curso, com as etapas a serem riscadas | `plano-visual.jpg` |
| `navegador no preview e inspect.jpg` | O preview a navegar na web (abas e barra de endereço) com o **modo inspecionar** ligado: o cartão do elemento ao lado, com nome, descrição do glossário, fonte, cor, classes e localização no código | `preview-navegador-inspecionar.jpg` |
| `notas.jpg` | As abas do caderno de notas — cada assunto na sua nota — com a varinha ao lado do título, e o painel das informações do projeto ao lado | `notas.jpg` |
| `vista ifc.jpg` | O modelo IFC da árvore, gerado pelo agente, aberto no visualizador | `visualizador-ifc.jpg` |
| `cards.jpg` | O terminal em modo cards, cada comando no seu cartão | `terminal-cards.jpg` |
| `paint foguete.jpg` | O Paint com o foguete desenhado e o raciocínio ao lado | `janela-paint.jpg` |
| `criando desenho paint.jpg` | O Paint com a casa desenhada e a explicação do que falhou antes de sair certo | — |
| `informacoes do projeto.jpg` | As informações do projeto: stack, dependências e a árvore com os totais | `informacoes-do-projeto.jpg` |
| `leitura ficheiros arvore.jpg` | A resposta a um memorial com imagens e tabelas | — |
| `raciocinio.jpg` | O raciocínio do agente com o log da sessão ao lado | `raciocinio.jpg` |
| `eureca!.jpg` | O raciocínio do agente a chegar a uma conclusão | — |
| `Captura de tela 2026-09-01 024505.jpg`, `terminal dinamico.jpg` | Interface antiga, de setembro | substituídas pelas novas |

As capturas usadas no README estão copiadas para `coder/docs/interface/` (nomes em minúsculas, sem acentos) e reduzidas a 1920 px de largura, sem recorte — todas a janela inteira. Numa versão anterior o `navegador no preview` chegou a ser recortado, e a cópia ficou presa nessa forma: trocar o conteúdo debaixo do mesmo nome não chega, porque a imagem do README é servida por um endereço em cache — foi preciso mudar o nome para `preview-navegador-inspecionar.jpg`. O texto do cartão do modo inspecionar fica pequeno nessa largura, e é por isso que ele também existe aqui no original, para quem precisar de o ler. Um recorte apertado chega a cortar listas a meio, e a leitura passa a ser a de um fragmento em vez da de um ecrã. Os originais ficam aqui, com o nome de origem. O `gimp.jpg` do README não vem daqui: é um fotograma do vídeo `criando desenho gimp.mp4`, porque a cena montada por script só aparece em movimento.
