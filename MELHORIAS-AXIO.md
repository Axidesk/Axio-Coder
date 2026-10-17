# Melhorias do Axio Coder (anotadas fora da pasta do Axio)

Este arquivo **não faz parte do produto**. É a lista de atritos que apareceram enquanto
trabalho neste projeto, para serem corrigidos quando eu voltar a abrir a pasta do Axio.

Regra: só entra aqui o que é **global** (serve a qualquer projeto) e foi **sentido de
verdade** na rodada — não é lista de desejos.

---

## 2026-10-15

### 1. A pasta `.axio` é criada dentro da pasta do usuário
Confirmado em `D:\Dropbox\2 - Startup\AXIO ADVERTISING\.axio\busca.txt` (log de busca).
O modo "outro projeto" promete que nada meu é escrito na pasta dele, mas o log de busca
entra lá na mesma.
**Corrigir:** escrever o log de busca no DATA_DIR do Axio, não na pasta do projeto aberto.

### 2. `tool_verificar_dependencias(pacote=...)` devolve o inventário inteiro
Pedi 6 pacotes (um por chamada) e recebi, nas 6, a lista completa de 211 pacotes
instalados com os 91 desatualizados e os 24 travados — o mesmo texto repetido seis vezes.
Isso enche o contexto e esconde a única linha que eu queria.
**Corrigir:** quando a chamada é por um pacote específico, responder SÓ esse pacote;
o inventário completo fica para a chamada sem argumento.

### 3. O relatório confunde o gestor de pacotes com a versão
Saiu, literal: `fastapi: NAO esta instalado. Ultima publicada: pip 0.143.2` e
`argon2-cffi: ... pip 25.1.0`. O rótulo "pip" colado ao número faz parecer que a versão
é do pip, não do pacote.
**Corrigir:** no caminho de pacote ausente, escrever "última publicada no PyPI: <versão>"
e (quando souber) o link da release.
**Repetido a 2026-10-15, na pasta AXIO ADVERTISING:** pedi `pillow` e voltou
`pillow: NAO esta instalado. Ultima publicada: pip 12.3.0` — o número era mesmo do Pillow,
mas o rótulo dizia "pip". Para não instalar uma versão adivinhada tive de ir ao
`pypi.org/pypi/pillow/json` confirmar 12.3.0 à mão.

### 4. `tool_estado_git` numa pasta sem repositório
Devolve o erro corretamente, mas podia fechar o ciclo: dizer logo que `tool_publicar_git`
com `criar=True` cria o repositório ali e perguntar/indicar o caminho.
**Corrigir:** acrescentar a ação sugerida na própria resposta do erro.

### 5. `tool_executar_python` corre no interpretador do Axio, não no venv do projeto
Num projeto com venv próprio (este caso), o trecho rebentou com `ModuleNotFoundError: argon2`
porque correu no Python do Axio, que não tem as dependências do projeto. Perdi uma volta e
tive de escrever uma sonda descartável na raiz só para correr o mesmo teste no venv certo.
Isto bate em QUALQUER projeto Python que não seja o Axio — é o caso normal, não a exceção.
**Corrigir:** `tool_executar_python` aceita um parâmetro com o interpretador (ou deteta o
`.venv` da pasta aberta e usa-o por omissão), para provar comportamento com as dependências
do projeto sem sair da ferramenta.

### 6. `tool_observar_preview` não sabe carregar um endereço
Chamei `acao='carregar'` e a ferramenta recusou: essa ação só existe em `tool_operar_preview`.
São duas ferramentas que falam do mesmo preview e não partilham as ações.
**Corrigir:** aceitar 'carregar' também na observação, ou dizer na descrição onde ele vive.

### 7. `tool_substituir_lote` com vários ficheiros tenta TODOS os blocos em TODOS
O `@ caminho` só vale para o bloco imediatamente abaixo dele. Escrevi cinco blocos seguidos para o
`painel.js` com um único `@` no topo: os blocos seguintes foram tentados também nos outros dois ficheiros,
e o lote abortou nesses ("o trecho do bloco 3 não foi encontrado"). Saíram 1 de 3 ficheiros gravados e
perdi uma volta a repetir os outros à mão.
**Corrigir:** ou cada bloco leva o seu `@`, ou o `@` abre uma secção (todos os blocos até ao próximo `@`
pertencem àquele ficheiro) — e a descrição deve dizer qual dos dois é.

### 8. O print do preview sai preto no que está fora do ecrã
Pedi o print da secção do formulário — que existia, com 691 px de altura e os campos lá dentro — e a
imagem veio inteiramente preta, duas vezes, mesmo depois de rolar até lá. O que está fora da viewport
não aparece pintado na captura. A saída foi fotografar o ecrã do sistema (`tool_capturar_print`), o que
obriga a janela do preview a estar à frente.
**Corrigir:** rolar até ao elemento e deixar passar um quadro antes de capturar — ou fazer a captura com
a página inteira, como o motor do Chromium já sabe fazer.

### 9. `tool_observar_preview` não tem 'mostrar'
Tentei `acao='mostrar'` no `observar` e a ferramenta recusou: essa ação só existe no `operar`. São duas
ferramentas que falam do mesmo preview e não partilham as ações (é o mesmo atrito do item 6).
**Corrigir:** partilhar as ações comuns entre as duas, ou dizer na descrição de cada uma onde vive o quê.

### 10. Âncora repetida no `tool_substituir_lote` derruba o lote inteiro e não diz onde
Passei cinco blocos para o `painel.py` e o terceiro tinha um trecho que também existe noutra rota
(as mesmas três linhas de período + retrato da frota). A resposta foi só
`o trecho do bloco 3 ocorre 2 vezes no ficheiro (ancora ambigua)` — nem as linhas, nem o trecho, e
**nada foi gravado**, incluindo os blocos 1, 2, 4 e 5 que estavam certos. Perdi uma volta a reescrever
tudo com uma âncora mais longa.
**Corrigir:** ao abortar, dizer em que linhas cada ocorrência está (ou mostrar as duas com contexto),
e deixar claro que nenhum bloco entrou — hoje isso só se descobre a reler o ficheiro.

### 11. Ação que falha porque a página já navegou devolve "elemento não encontrado"
Estava na página de entrada, cliquei num cartão que entrou na conta e mudou de página (comportamento
certo), e o gesto seguinte respondeu `Nenhum elemento encontrado para #email.` — a mesma mensagem que
um seletor mal escrito daria. Perdi duas chamadas a desconfiar do seletor, quando o que faltava era
saber que a página já não era aquela.
**Corrigir:** ao não encontrar o alvo, dizer em que endereço a página está agora (e se navegou desde o
último gesto), para o erro distinguir "seletor errado" de "mudaste de página".

### 12. `tool_observar_preview(print)` promete `regiao` por seletor e recusa
A descrição diz que a `regiao` pode ser um seletor ou um retângulo. Passei `regiao='.lp-heroi'` e
voltou `ERRO: Regiao invalida: use x,y,largura,altura.` — sem dizer onde estava o elemento nem qual
seria o retângulo dele, obrigando a uma segunda chamada (`acao='elemento'`) só para descobrir as
coordenadas à mão.
**Corrigir:** aceitar o seletor e resolver o retângulo internamente — ou, se não aceitar, tirar a
promessa da descrição e devolver o retângulo do alvo no próprio erro.

### 13. `tool_operar_preview(roteiro)` não diz o formato dos passos
A descrição fala em "dez gestos numa só chamada" mas não diz como escrever `passos`. Tentei uma
lista legível, um gesto por linha, e recebi `'passos' nao e JSON valido`. Tentei JSON e o passo
`esperar` foi recusado (não está na lista, embora o roteiro de `tool_operar_janela` o tenha), o que
custou uma segunda volta só para descobrir a lista de ações aceitas.
**Corrigir:** um exemplo de `passos` na descrição (dois gestos bastam) e a lista de ações aceitas no
próprio erro — o resto eu deduzo.

### 14. `tool_substituir_texto` aceita uma âncora que não existe e a mensagem não ajuda
Escrevi a âncora de cabeça (uma linha que supunha existir no ficheiro) e a resposta foi
`Nao ha nenhuma linha parecida com a ancora neste ficheiro - confirme o FICHEIRO` — apontando para o
ficheiro, que era o certo. O que faltava era o contrário: em vez de "confirme o ficheiro",
mostrar as duas linhas mais próximas da âncora (ou o início do ficheiro), porque o erro típico é a
âncora, não o caminho.
**Corrigir:** quando a âncora não casa, devolver 3-4 linhas reais do ficheiro à volta do ponto onde
ela falhou — uma chamada de leitura a menos por cada escrito.

### 17. `tool_executar_processo` arranca no cwd errado quando não se passa `cwd`
Passei `cwd="."` e o processo arrancou na pasta do Axio (`CODER\coder`), não na pasta aberta: o servidor
do projeto não subiu (`can't open file ...\coder\executar.py`) e só se percebeu na saída do processo.
**Corrigir:** sem `cwd`, usar a pasta do projeto aberto — e nunca a pasta do Axio.

### 18. `tool_medir_pintura` não encontra ficheiros criados nesta sessão
Criei uma sonda na raiz e depois na pasta do frontend, e a ferramenta respondeu `ficheiro nao encontrado`
às duas, embora o `tool_listar_pasta` os visse — parece usar a lista de ficheiros do arranque.
**Corrigir:** varrer o disco no momento do pedido, não usar um índice antigo.

### 19. `tool_medir_pintura` não resolve os `link href` absolutos da própria app
Medindo `src/frontend/index.html`, o CSS (`/recursos/css/...`) não carrega — devolveu `CSS: nenhum` e 25
variáveis por definir, logo a paleta e a geometria medidas não eram as do produto (o aviso é honesto, mas
a medição sai inútil). A saída foi montar uma sonda com caminhos relativos **e** um iframe de 390px, para
o `@media` do celular disparar a sério.
**Corrigir:** mapear `/recursos/` para a pasta do frontend do projeto aberto (é o que o servidor faz) e
aceitar uma largura de viewport como já aceita `largura`/`altura`.

### 20. `tool_observar_preview(print)` devolve preto quando a página não está a compor
Com o DOM todo montado (marca, secções, canvas do WebGL), o `print` voltou duas vezes completamente preto
— sem avisar que a captura não valia. O caminho que funcionou foi o `tool_capturar_print` do sistema,
depois de trazer a janela à frente.
**Corrigir:** quando a captura sair uniforme (tudo preto ou tudo de uma cor), dizer isso no retorno em vez
de entregar a imagem como boa — e sugerir o `tool_capturar_print`.

### 15. `tool_substituir_lote` deita fora os blocos que já casaram
Numa edição de 7 blocos, o último (a linha do import) não casou e **nada foi gravado** — incluindo os
6 anteriores, que estavam certos e já tinham sido confirmados pelo ficheiro. Reescrevi os 7.
**Corrigir:** aplicar os blocos que casaram e devolver só o que falhou como pendente, ou — se a
atomicidade for mesmo desejada — dizer no erro quantos blocos já estavam prontos, para não se
recalcular tudo.

### 16. `tool_executar_python` corre fora da pasta do projeto
`from _gerar import ...` falha com `ModuleNotFoundError` mesmo com o ficheiro em `gerados/pecas/`,
porque o trecho corre da pasta temporária e o cwd não é a raiz do projeto aberto. A saída foi pedir o
trabalho a `tool_executar_processo` com o caminho do venv — o duplo do caminho que a ferramenta devia
resolver sozinha.
**Corrigir:** correr o trecho com o cwd na raiz do projeto (e, de preferência, com o `sys.path` a
incluí-la), como já faz o `tool_executar_js`.

### 21. Medir no preview depois de editar um módulo ES mede a versão ANTIGA, sem avisar
Editei `js/rodape.js`, carreguei a página **sem cache** e as medições continuaram a mostrar o componente
antigo (etiquetas de texto onde já só havia ícones). O disco estava certo e o servidor servia-o certo —
`fetch('/recursos/js/rodape.js', {cache:'no-store'})` provou-o — mas a sonda (um iframe novo, logo um
documento novo) recebia o módulo velho da cache de módulos do processo, sem revalidar. Gastei 4 chamadas
a desconfiar do código errado antes de perceber que media o ficheiro antigo.
**Corrigir:** o `recarregar`/`carregar` do preview deve invalidar também os módulos ES do processo (não
basta recarregar o documento de topo), ou — no mínimo — o `avaliar` deve poder dizer que versão de um
módulo está viva, para eu não medir código velho nem acusar um defeito que já foi corrigido.

*(O item 20 repetiu-se nesta rodada, no preview do painel: `print` devolveu tudo preto duas vezes e a
saída voltou a ser a captura do sistema.)*

### 22. `tool_executar_processo` com caminho relativo falha e não diz de onde correu
`.venv\Scripts\python.exe executar.py` devolveu só `O sistema não pode encontrar o caminho especificado`
— sem dizer em que pasta tentou, nem qual era o cwd assumido. O comando é o mesmo que corre à mão na
raiz do projeto; a diferença não está no comando, está em onde ele foi lançado, e isso a ferramenta não
mostra. Só o caminho absoluto da pasta resolveu.
**Corrigir:** devolver o cwd usado e o caminho já resolvido no erro de arranque, e (melhor) aceitar o
venv do projeto aberto por um nome curto — `venv:python` — em vez de eu ter de escrever o caminho todo.

### 23. `avaliar` com `durante` acusa "a pagina nao respondeu em 8s" numa página viva
`tool_observar_preview(acao='avaliar', durante=10000, intervalo=2000)` respondeu que a linha principal
estava ocupada com código síncrono (a mensagem sugere um leitor de IFC em WASM). A página era o painel do
projeto, sem IFC nenhum, e a **mesma** expressão, sem `durante`, respondeu no mesmo segundo. O bloqueio
era do próprio modo de amostragem, não da página.
**Corrigir:** quando o `durante` não conseguir arrancar, dizer isso claramente (em vez de culpar a
página) e cair para a medição única — a informação sai, só não vem em série.

## 2026-10-16

### 24. `tool_operar_preview(acao='carregar')` recusa um caminho da própria aplicação
`carregar` com `alvo='/contato'` responde `ficheiro do projeto nao encontrado: /contato` — trata o alvo
como ficheiro do disco, e não como endereço relativo ao que o preview já está a servir. O mesmo alvo em
URL completa (`http://127.0.0.1:8099/contato`) funciona. Numa página da própria app, o caminho curto é o
que sai naturalmente à mão.
**Corrigir:** quando o alvo começa por `/`, resolver contra a origem que o preview já tem (e só cair para
o ficheiro do projeto se não houver origem).

### 25. `print` do preview devolve preto — o atalho que resolve é a geometria da view
Quarta rodada com o mesmo sintoma: `tool_observar_preview(acao='print', regiao=...)` entregou uma imagem
100% preta de uma região que eu sabia estar pintada (números do DOM a confirmá-lo). O caminho que
funcionou foi `tool_capturar_print` sobre o ecrã, com a região calculada a partir de
`window.screenY` da página (esse valor corresponde ao topo real da view e o eixo Y bate 1:1 no print do
sistema). O `screenX`, esse, mente: devolveu 328 quando a view começava por volta de 900 no ecrã — o
`WebContentsView` reporta a posição da janela-pai, não a sua.
**Corrigir:** o `print` do preview devia cair sozinho para a captura do sistema quando o quadro vier
vazio, e o `avaliar` devia poder dizer a posição real da view no ecrã (não só `screenX/screenY`), para a
região sair certa à primeira.

### 26. `tool_substituir_lote` recusa o lote inteiro quando o texto acaba em quebra de linha
Mandei um lote de 3 blocos com o marcador final `>>>>>>> NOVO` seguido de uma quebra de linha (fim de
string natural de quem escreve o pedido num editor). A ferramenta respondeu
`ERRO: o ultimo bloco (3) nao foi fechado com '>>>>>>> NOVO'` e nao gravou nada — a quebra depois do
marcador e lida como se o marcador nao estivesse la. Nao ha forma de saber pelo erro que o problema e
um `\n` a mais.
**Corrigir:** aceitar espaco/quebra depois do ultimo `>>>>>>> NOVO` (e, em geral, apara-los antes de
comparar). Um lote de 3 blocos nao devia morrer por um `\n` no fim.

### 25-bis. O `print` do preview funciona quando a regiao e um retangulo simples
Nesta rodada o mesmo `print` (regiao `0,0,900,620`, so numeros) entregou a imagem certa a primeira.
O que falhou nas rodadas anteriores era sempre regiao em formato de retangulo com dimensoes grandes ou
imagem muito clara/branca na area pedida. Fica o registo: nao e o `print` inteiro que esta morto —
e um caso dele.

### 27. `tool_medir_pintura(ficheiro=...)` nao acha um HTML criado na propria pasta do projeto
Criei `src/frontend/sonda-mobile.html` (e depois `_sonda_mobile.html`) e a ferramenta respondeu
`ficheiro nao encontrado` nas duas tentativas, com o ficheiro no disco e legivel pela `tool_ler_arquivo`.
Sem saber o que ela aceita, o caminho vira tentativa e erro.
**Corrigir:** aceitar o caminho relativo a pasta do projeto (como a `ler_arquivo` aceita) e, quando nao
achar, dizer o caminho absoluto que tentou — a diferenca entre "nao existe" e "procurei no sitio errado"
tem de sair do proprio erro.

### 28. Nao ha como medir o layout a uma largura de telemovel
O `observar/operar_preview` mede sempre a view no tamanho real da janela; nao existe pedido de largura.
Para provar o CSS de celular (media queries) resta montar um `iframe` de 390px dentro da pagina e medir
la dentro — um contorno que gasta 3-4 chamadas e que, numa pagina com `polling` e video, chegou a
bloquear o fio principal ate a `avaliar` estourar os 8s. Medir a interface no telemovel e uma das
perguntas mais frequentes e e a que nao tem instrumento.
**Corrigir:** um parametro de largura/altura (emulacao de viewport) no `observar_preview`/`operar_preview`
resolvia a media query de uma vez, sem iframe nem sondas.

## 2026-10-16

### 29. Medir uma pagina cujo CSS nao carregou devolve numeros falsos, e nada avisa
Montei um `iframe` com o markup real e dois `<link>` para o CSS do projeto, medi geometria celula a
celula e recebi **tudo empilhado numa coluna** (4 celulas, 4 alturas diferentes). Diagnostiquei a causa
no CSS e mudei a folha. So depois descobri que os dois `<link>` respondiam **404** (o caminho levava
`/css/...` em vez de `/recursos/css/...`) e o que eu estava a medir era a pagina **sem estilo nenhum**:
a medicao era irrepreensivel e a conclusao, inventada.
O instrumento nao distinguiu "elemento empilhado" de "folha de estilo ausente" - e eu confiei nele.
**Corrigir:** ao avaliar/medir, sinalizar sempre os pedidos de recurso que falharam (CSS/JS/404) e, quando
a pagina tiver `styleSheets` com 0 regras, dize-lo em voz alta. Uma folha que nao carregou tem de
aparecer no resultado, senao qualquer medicao vira ruido com cara de prova.

### 30. `operar_preview(clicar)` afirma "a repeticao resolveu" sem ter resolvido nada
No clique de `#btn-entrar` o retorno disse: *"Nada detetavel mudou na pagina... o gesto foi repetido uma
vez: a 1a tentativa nao mexeu na pagina (alvo a meio de uma re-renderizacao) e a repeticao resolveu."*
A verdade era outra: o pedido de login tinha rebentado com **500** (`db is locked`) e a pagina nunca saiu
do sitio - a segunda tentativa falhou igual. O relatorio deu por bom um gesto que falhou, e o erro 500
so apareceu porque fui ler a consola por conta propria.
**Corrigir:** a repeticao so pode ser dada como "resolveu" se houver mudanca observavel (URL, DOM,
valor, pedido com status de erro na rede). Sem isso, dizer que repetiu e continua igual - e mostrar o
pedido cuja resposta falhou.

## 2026-10-17

### 31. Nao ha como medir a interface numa largura de telemovel
O `observar_preview` mede a janela que estiver aberta (955px no meu caso) e nao aceita largura nem
altura. Para provar uma media query tive de injectar um `<iframe>` de 390px **dentro** da propria
pagina com um `avaliar`, ler as medidas la dentro e so depois remover o quadro. Funcionou, mas um
iframe a mais na pagina do utilizador a cada medicao e um risco que nao devia existir.
**Corrigir:** um parametro de largura/altura (emulacao de viewport) no `observar_preview` e no
`operar_preview` resolvia isto de uma vez, sem iframe nem sonda.

### 32. `avaliar` devolve lista vazia quando a pagina ainda esta a desenhar, sem avisar
Depois de clicar num icone do menu, o JS que procurou os grupos correu antes de a pagina terminar e
devolveu `{grupos: [], ligacoes: []}` - que se le como "nao existe" quando a resposta certa era
"ainda nao ha". Tive de repetir a medicao com uma espera a mao.
**Corrigir:** quando a expressao devolve uma colec cao vazia e a pagina tem pedidos em curso, dizer
isso ("a pagina ainda esta a carregar: N pedidos abertos") em vez de entregar o vazio como resultado.

### 33. Um teste em `tool_executar_python` nao ve as dependencias do projeto
O trecho correu no interpretador do Axio, onde o `sqlalchemy` do projeto aberto nao existe
(`ModuleNotFoundError`), e o mesmo aconteceu com o caminho de import do `banco.py`. Acabei a criar um
script de sonda na raiz e a corre-lo pelo `tool_executar_processo` com o venv do projeto e o `cwd`
explicito - tres voltas para uma limpeza de 3 linhas.
**Corrigir:** correr o trecho com o `cwd` na raiz do projeto aberto e com o venv DESSE projeto no
`sys.path` quando ele existir (como o `tool_executar_js` ja faz com o cwd), ou aceitar um parametro
`interpretador`.

## 2026-10-18

### 34. `avaliar` desiste em 8s e culpa o leitor de IFC quando a pagina so esta ocupada
Uma medicao que trocava de secao tres vezes e lia os grupos de cada uma rebentou com: *"a pagina nao
respondeu em 8s: isso e a linha principal ocupada com codigo sincrono (um leitor a converter -
tipicamente o IFC em WASM) e nao uma avaria do depurador"*. Nao havia IFC nenhum na pagina: eram as
consultas da propria troca de secao mais o mapa. Tive de partir a medicao em **quatro chamadas** com
esperas entre elas, e cada chamada relatou um pedaco do que uma so devia ter dado.
O diagnostico foi inventado e o limite e curto para uma pagina que faz pedidos.
**Corrigir:** o tempo do `avaliar` tem de ser configuravel (ou esperar que os pedidos em curso
terminem) e, quando estourar, dizer o que a pagina estava a fazer - pedidos abertos, tempo desde o
ultimo, seletor que faltou - em vez de atribuir a culpa a um leitor que nao existe.

### 35. `operar_preview(clicar)` repete o gesto sozinho e DUPLICA o efeito de um botao que escreve
Cliquei uma vez no botao "Publicar nos tablets" e a resposta disse: *"Nada detetavel mudou na pagina
(...) O gesto foi repetido uma vez: a 1a tentativa nao mexeu na pagina (alvo a meio de uma
re-renderizacao) e a repeticao resolveu"*. No servidor ficaram **duas** campanhas iguais, com as
duas pecas. O botao estava a publicar (leva ~1s) e o painel so mostrava "A subir..." - o retry
automatico mandou o segundo POST.
Um clique que cria registos nao pode ser repetido por conta propria: sem um parametro explicito
(`repetir=false`, ou `vezes=N`), a repeticao e um efeito colateral invisivel. E a nota "a repeticao
resolveu" e falsa quando o alvo simplesmente ainda nao tinha acabado de trabalhar.
**Corrigir:** por omissao, UM gesto = UM evento; a repeticao passa a ser pedida por mim, e o relato
de "nao mexeu na pagina" nao pode afirmar que resolveu sem mudanca observavel.

### 36. `tool_executar_processo` anuncia uma porta que nao e a do servidor
Arrancar o projeto devolveu *"(porta sugerida via env PORT/FLASK_RUN_PORT: 5001)"* e, 30s depois,
*"[axio] servidor nao respondeu em 30s; abra manualmente: http://127.0.0.1:5001"*. O servidor estava
no ar e a servir bem - na porta 8099, que vem do proprio projeto (`PROVA_PORTA`), nao do ambiente da
ferramenta. A mensagem manda abrir um endereco morto e sugere uma avaria que nao existe.
**Corrigir:** dizer a porta que a ferramenta espera e a que o processo abriu de facto (ler do
primeiro log/socket do processo) e, ao falhar o ping, indicar onde procurou.

### 37. Reincidencias confirmadas a 2026-10-18 (nada de novo, mas custou tempo de novo)
- **#22 (cwd):** `tool_executar_processo(comando="python executar.py", cwd=".")` arrancou o processo
  na pasta do **Axio** (`CODER\coder`), nao na pasta do projeto aberto, e o erro so apareceu 30s
  depois no log (`can't open file ...\\CODER\\coder\\executar.py`). Reiniciar o servidor exigiu
  duas chamadas e um `cwd` absoluto escrito a mao. Um `cwd` relativo devia resolver-se sempre na
  pasta do projeto aberto, e a ferramenta devia dizer **onde** vai correr antes de correr.
- **#34 (`avaliar` a 8s):** medir quatro trocas de secao rebentou outra vez no limite de 8s. Tive de
  partir a medicao em duas chamadas. Ja anotado; continua a ser o atrito mais frequente do dia.
- **#31 (sem emulacao de viewport):** medi tudo o que esta rodada provou a 390px **dentro de um
  iframe injectado na propria pagina do utilizador** - quatro quadros destes deixados e removidos.
  A falta de um parametro de largura continua a ser o que mais me faz inventar contorno.

### 38. Com o preview dentro da app, nao ha como voltar a outra pagina pelo instrumento
Depois de entrar no painel, `tool_operar_preview(acao='carregar', alvo='<url>/entrar')` responde
*"Preview a carregar <url>/entrar"* e a pagina seguinte continua a ser o painel - duas tentativas
seguidas. O `avaliar` com `location.href = "/entrar"` tambem nao mudou de pagina. A unica forma de
chegar ao login foi **sair pela propria interface do site** (o botao de sair), que navega sozinho.
Ou seja: nao consigo medir a pagina de entrada enquanto estou dentro do painel, sem antes desfazer a
sessao do utilizador.
**Corrigir:** o `carregar` tem de navegar mesmo que o preview ja esteja numa pagina da mesma app
(dizer o resultado real: URL final, e nao a intencao), ou expor `location.assign` no `avaliar` como
forma de navegacao explicita.

### 39. `avaliar` que provoca navegacao devolve "Inspected target navigated or closed" sem plano B
Um `avaliar` cujo codigo clica num botao que muda de pagina morre com
`ERRO: Falha na acao avaliar: Inspected target navigated or closed`. E o esperado tecnicamente, mas a
mensagem nao diz se a acao chegou a correr (o clique correu, e o servidor registou-o) nem sugere o
passo seguinte. Perdi uma chamada a repetir a medicao por achar que nada tinha acontecido.
**Corrigir:** separar "o codigo correu e a pagina navegou a meio" de "nao consegui avaliar", e
devolver o que se sabe (URL nova, se o clique foi disparado) em vez de so o erro do alvo.

### 40. `print` e `avaliar` nao partilham o mesmo referencial de coordenadas
Medi a tabela com `avaliar` (getBoundingClientRect) e deu `top=499`; pedi o `print` de `470` e a imagem
mostrou o que estava ABAIXO da tabela, como se a regiao fosse contada de outro sitio. Repeti com a
mesma janela de 3 chamadas e nunca acertei de primeira: o `print` cortado a uma faixa apanha conteudo
que nao corresponde ao rect medido no mesmo instante (a pagina repinta a cada 4s e o layout mexe).
**Corrigir:** aceitar `regiao` por SELETOR (a MELHORIA 12 ja pede isto) ou devolver a imagem de um
elemento por nome, e dizer no resultado a que referencial a regiao foi aplicada (viewport ou pagina).
Um `print` que aceitasse o seletor dispensava 3 chamadas por cada vez que preciso de julgar um desenho.

### 41. Medir na largura de um celular nao tem caminho (reincidencia do 29)
Para provar que as colunas de uma tabela ficam alinhadas a 390px tive de escrever uma pagina de sonda
DENTRO do projeto do utilizador, servi-la pelo monte estatico do proprio app, medi-la por dentro de um
iframe e apaga-la no fim. Cinco chamadas de instrumento (salvar, descobrir o monte, carregar, avaliar,
apagar) para responder a "isto cabe no telemovel?" - e um ficheiro meu entrou e saiu da pasta dele.
A isto somou-se um atrito pequeno: `operar_preview(acao='carregar')` recusou o caminho
`/sonda-mobile.html` e so aceitou o endereco completo, sem a mensagem o dizer.
**Corrigir:** um parametro de largura/altura (emulacao de viewport) no `observar_preview`/`operar_preview`
resolvia isto numa chamada e sem ficheiro nenhum no projeto de quem me abre a pasta.

### 42. `observar_preview(print)` volta a sair preto quando a pagina ja foi rolada (reincidencia do 20/33)
Para julgar com os olhos a seccao nova da pagina inicial medi a posicao do elemento (top 20, esquerda 34,
880x737, dentro da janela de 892) e pedi o print exactamente dessa regiao. Saiu **preto**, duas vezes -
antes e depois de recarregar. O que ja funciona: a mesma regiao, sem rolar a pagina, sai certa.
O instrumento entrega a imagem como boa e nao diz que nao presta.
**Corrigir:** quando a captura vier uniforme (tudo preto ou tudo de uma cor), dizer isso no retorno em vez
de a entregar como valida, e sugerir o `tool_capturar_print` do sistema. Uma imagem preta nao e um
resultado - e um instrumento avariado a passar por prova.

### 43. `tool_observar_preview(avaliar)` corre antes de a pagina acabar de montar e devolve `null`
Logo depois de um `carregar`, a primeira expressao rebentou com
`TypeError: Cannot read properties of null (reading 'getBoundingClientRect')` porque o elemento ainda
nao existia; a chamada seguinte, identica, respondeu bem. Nao houve espera nem aviso - o erro aponta
para a minha expressao quando a causa era o momento. (Mesma familia do item 32.)
**Corrigir:** o `avaliar` devia esperar o `load`/`DOMContentLoaded` da pagina pedida, ou dizer quantos
pedidos estao abertos quando a expressao falha logo a seguir a uma navegacao.

## 2026-10-19

### 44. `operar_preview(clicar)` diz "nada detetavel mudou" quando a pagina MUDOU
Cliquei no cabecalho de um grupo recolhivel no painel e a resposta foi *"Nada detetavel mudou na pagina
(175 elementos, 27 sem caixa)"*. A medicao seguinte provou o contrario: o grupo abriu e o irmao fechou
(`abertas: [["Cadastrar veiculo", false], ["Meus veiculos", true]]`). Como a ferramenta conta elementos,
uma transicao que so muda classes **dentro de um `content-visibility: hidden`** passa despercebida - e a
nota "nada mudou" e perigosa: convida a repetir o gesto, e aqui repetir seria fechar outra vez o que eu
queria aberto (o item 35 mostra o caso em que repetir duplicou registos no servidor).
**Corrigir:** medir tambem o atributo `hidden`, as classes do alvo e dos irmaos, e a altura do que abriu,
em vez de contar elementos do documento; e nunca afirmar "nada mudou" sem olhar para o alvo que recebeu
o gesto.

### 45. `operar_preview(roteiro)` nao diz em que formato se escrevem os passos
Tentei `escrever #email x` numa linha por gesto e a resposta foi *"'passos' nao e JSON valido"*. O erro
traz o exemplo certo (é uma lista de objetos), mas a descricao da ferramenta nao o diz - e o formato
"uma linha por gesto" é o que a `tool_operar_janela(roteiro)` usa, logo a mesma palavra pede dois
formatos diferentes nas duas ferramentas.
**Corrigir:** escrever o formato na descricao (ou aceitar os dois - um `escrever` por linha é o mais
natural de ditar).

### 46. Correr codigo do projeto com `tool_executar_python` (reincidencia do 20 e do 36)
O `tool_executar_python` corre com o interpretador do Axio, que nao tem SQLAlchemy - e o projeto aberto
tem. Para apagar 75 registos de teste tive de criar uma sonda e corre-la com `tool_executar_processo` e
o caminho do venv do projeto escrito a mao. ``tool_executar_js`` ja corre com o cwd na raiz do projeto;
o de Python devia fazer o mesmo e, existindo `.venv` na pasta aberta, usar ESSE interpretador.
**Corrigir:** escolher o interpretador pelo projeto aberto (`.venv/Scripts/python.exe` quando existir),
com o `sys.path` a incluir a raiz.

---

## 2026-10-20

### 47. O relogio que eu recebo traz a HORA mas nao a DATA (pedido do utilizador)
O `[SISTEMA-RELÓGIO]` injetado a cada chamada diz `Chamada nº N | Hora atual: 22:52:15 | Tempo decorrido`
- e so. Falta o DIA, o MES, o ANO e o dia da semana. Sem isso eu nao tenho nocao da minha posicao no
tempo: uma noticia de 2010, um preco de 2018 ou uma versao de 2021 leem-se como atuais, e a pesquisa na
web sai errada por isso (e o erro nao se nota - parece uma fonte legitima). Foi o utilizador que apontou.
**Corrigir:** injetar a data completa junto ao relogio: `2026-10-20 22:52:15 (segunda-feira)`. Barato e
resolve uma classe inteira de erro silencioso, tanto em pesquisa como no julgamento de memoria antiga
(uma nota curada de "hoje" tem de poder ser confrontada com a data real).

### 48. `tool_executar_processo` recusa o interpretador do projeto com argumentos
`python _sonda.py` correu (o PATH resolveu para o venv do projeto, por sorte); `.venv\Scripts\python.exe -u
_sonda.py` foi RECUSADO pela allowlist - *"Uso de 'python' nao permitido"*. Ou seja: a unica forma de eu
fixar o interpretador do projeto e proibida, e a que funciona depende de o PATH estar certo, sem nada o
dizer. Reincidencia do 5/16/46 (pedir o venv do projeto aberto), agora com um agravante: quando falha,
nao ha caminho alternativo que eu possa escrever sozinho.
**Corrigir:** aceitar o interpretador do venv da pasta aberta (com ou sem argumentos) e dizer, na resposta,
QUAL interpretador correu - assim uma sonda que corre no Python errado deixa de parecer que correu bem.

### 49. Landing page nao leva texto explicativo (regra de escrita, nao de codigo)
Repetiu-se varias vezes neste projeto e o utilizador teve de corrigir cada uma: "o contato e pelo
formulario", "acertada caso a caso com a nossa equipe", "Cadastro simples do carro: modelo, matricula e o
seu telefone". A ultima e o exemplo perfeito do erro - o item devia ser "Cadastro simples" e mais nada.
A tentacao e explicar o mecanismo onde a pagina existe para VENDER, e cada frase a mais tira forca a que
interessa. Regra pratica ja registada nas preferencias (`landing-saas`): **se a frase descreve uma funcao,
sai; se faz o visitante reconhecer-se, fica.** O detalhe vive no painel, no balao de ajuda ou na janela -
nunca na landing.
**Corrigir:** nao e codigo - e o habito de escrever a landing primeiro como venda e so depois como produto.
Antes de entregar uma landing, reler cada linha com a pergunta "isto ajuda alguem a querer, ou so explica?".

### 50. Produto novo nasce com o CONJUNTO de paginas, nao com uma peca so
O primeiro esboco da Vitrine saiu como pagina de teste interno: sem nome proprio, sem rodape, com textos a
explicar o mecanismo, e sem login nem contacto - essas vieram so quando ele pediu. Deu uma reconstrucao
inteira depois, e o utilizador disse-o assim: *"na primeira entrega vc entregou algo muito rustico, poderia
ja ter entregue algo muito melhor"*.
**Corrigir:** quando o pedido for um SaaS/produto/site com pagina inicial, entregar LOGO o conjunto
completo ainda que o escopo seja minimo: landing (heroi com frase de venda, seccoes curtas, rodape de
empresa em TODAS as paginas, login e contacto). O escopo pequeno limita o CONTEUDO, nunca o ACABAMENTO -
efeitos, transicoes e hierarquia sao a mesma quantidade de codigo feita ao contrario. Regra irma das
preferencias `landing-saas`.

### 51. `caminho='.'` nas ferramentas de GIT cai no repositorio do AXIO, nao no projeto aberto
Pedi o estado do git com o caminho por omissao e recebi o repositorio do proprio Axio
(`...\CODER\coder`, branch main com 520 commits por cima da tag) - nao o da pasta aberta, que e um
repositorio diferente. A publicacao seguinte com `caminho='.'` tentou um `git add MELHORIAS-AXIO.md`
DENTRO do repositorio do Axio, e so nao commitou por o ficheiro la nao existir.
**Risco:** um `tool_publicar_git` sem caminho explicito pode gravar material do projeto do utilizador dentro
do repositorio do Axio - e um erro que se descobre tarde, ja no remoto.
**Corrigir:** resolver o caminho relativo contra a PASTA DO PROJETO ABERTO (como fazem as ferramentas de
ficheiro) e, quando o repositorio encontrado nao for o dessa pasta, RECUSAR dizendo os dois caminhos.

---

## Estado do caderno

51 itens, 2026-10-15 a 2026-10-20, todos sentidos em trabalho real neste projeto. Os que mais voltaram
(por ordem de custo): **medir a interface numa largura de telemovel** (28/29/31/41 - continuo a ter de
montar um iframe de 390px dentro da propria pagina), **correr codigo do projeto** (5/16/33/46/48 - o
Python das ferramentas nao ve as dependencias do projeto), **o `print` do preview** (8/20/25/42 - devolve
preto e nao avisa) e **o cache de modulos ES** (21 e reincidencias - depois de editar, o preview mede a
versao ANTIGA sem dizer, e eu ja conclui uma vez a partir de codigo velho).
Ao aplicar isto, comecar por: (1) data no relogio, (2) largura de viewport na observacao/medicao,
(3) interpretador pelo venv do projeto, (4) recarregar modulos ES antes de medir. Estes quatro fecham a
maior parte das reincidencias.

**ESTA LISTA ESTA FECHADA** (1a leva a 2026-10-16, 2a a 2026-10-17): ver as duas seccoes APLICADO no
fim deste ficheiro. Nao ha item pendente.

---

## APLICADO a 2026-10-16 (1a leva, na pasta do Axio)

**Feito e provado:**

- **#47 data no relogio** - o `[SISTEMA-RELÓGIO]` passa a trazer `2026-10-16 23:25:48 (sexta-feira)`.
  (`src/backend/ai/loop.py:_relogio_do_prompt`, provado contra o calendario real.)
- **#5/#16/#33/#46/#48 correr codigo do projeto** - `tool_executar_python` usa o venv do PROJETO aberto
  (`.venv`/`venv`/`env`) quando existe, aceita um `interpretador` a mao e DIZ qual correu na resposta;
  `tool_executar_processo` aceita o `.exe` do venv com argumentos (`-u`), aceita o atalho `venv:python`,
  e o `cwd` relativo resolve na pasta do projeto (nao na do Axio).
- **#17/#22/#36 cwd e porta** - `_pasta_de_trabalho` resolve o relativo contra a pasta aberta e o erro
  diz para onde resolveu; a resposta diz sempre `pasta:` e o python usado; quando a porta nao responde,
  o aviso diz que porta se esperava e mostra o endereco que o processo escreveu.
- **#7 secção de `@` no lote** - `@ ficheiro` abre secção (todos os blocos ate ao proximo `@`); `@ *`
  fecha e volta a valer em todos. A descricao da ferramenta diz isto.
- **#10/#15 erro do lote** - a ancora ambigua lista as LINHAS de cada ocorrencia; o erro diz quantos
  blocos anteriores ja tinham casado.
- **#14 ancora nao encontrada** - alem do diagnostico de espacos, mostra 5 linhas reais do ficheiro por
  volta da linha mais parecida.
- **#26 quebra depois do marcador final** - linhas vazias fora de bloco deixam de derrubar o lote.
- **#1 log da busca** - `busca.txt` passou a `data/` do Axio (nunca mais dentro da pasta do projeto).
- **#2/#3 dependencias** - a consulta de um pacote devolve SO esse pacote; o rotulo passa a
  "Ultima publicada no PyPI: 12.3.0" (deixou de parecer a versao do pip).
- **#51 git** - `caminho` relativo resolve na pasta do PROJETO aberto (`.` deixou de cair no repo do Axio)
  e o erro sem repositorio sugere `criar=True`.

**Falta (proxima leva) - e o que exige a janela a correr para provar:**

- #28/#31/#37/#41 largura de viewport (`Emulation.setDeviceMetricsOverride` pelo CDP).
- #8/#12/#20/#25/#40/#42 print: regiao por SELETOR e avisar quando a captura sai uniforme.
- #21 cache de modulos ES ao recarregar; #29 folha de estilo que nao carregou tem de aparecer;
  #23/#32/#34/#43 `avaliar` com espera e tempo configuravel.
- #11/#30/#35/#44 gesto: um gesto = um evento, e "nada mudou" so com o alvo olhado.
- #6/#9/#13/#24/#38/#39/#45 acoes partilhadas entre observar/operar e o formato dos passos.
- #4 dica de `criar=True` na mensagem do `estado_git` sem repositorio (o `_base_do_repositorio` ja a
  escreve; falta o caminho que le o repo).
- #18/#19/#27 `medir_pintura`: achar ficheiro criado na sessao e mapear `/recursos/` do projeto.

---

## APLICADO a 2026-10-17 (2a leva: o preview inteiro)

**Feito e provado:**

- **#28/#31/#37/#41 medir na largura de um celular** - `tool_observar_preview` e `tool_operar_preview`
  aceitam `largura`/`altura` (e `mobile`): `Emulation.setDeviceMetricsOverride` com
  `dontSetVisibleSize`, aplicado so durante o pedido e limpo no fim (a janela nao e mexida). Provado
  num Chromium a serio (Edge headless + CDP): a 390 px o `matchMedia('(max-width:600px)')` passou a
  true, o `innerWidth` foi de 756 para 390, o pseudo-elemento mudou de conteudo e a cor mudou - e ao
  limpar voltou tudo a 756.
- **#8/#12/#20/#25/#40/#42 print** - o alvo e rolado para a vista e reenquadrado antes da captura; o
  que nao cabe na janela e capturado pelas coordenadas da PAGINA (`captureBeyondViewport`); sem alvo,
  o print e da pagina inteira. Medido: uma regiao a y=1200 de uma pagina cujo ecra tem 844 px de altura
  saiu desenhada (era exactamente o caso que saia preto). E a captura que sai uniforme passa a ser
  denunciada em Python (`uniformidade_da_imagem`, 0.985 da fatia sobre a cor dominante; print liso da
  1.0000, janela escura real do projeto da 0.9377) em vez de entregue como prova.
- **#23/#32/#34/#43 avaliar** - `espera` (ms antes de correr) e `tempo` (segundos antes de desistir, ate
  45); o diagnostico deixou de culpar um leitor que nao existe e passa a dizer `readyState`, pedidos em
  curso e tempo desde a ultima navegacao. Resultado vazio com pedidos em curso, e erro a menos de 1,5 s
  de uma navegacao, saem com aviso explicito.
- **#29 folha que nao carregou** - `estilo` e `avaliar` avisam quando a pagina tem folhas de estilo e
  ZERO regras legiveis: o caso em que a medicao esta irrepreensivel e a conclusao e inventada.
- **#11/#30/#35/#44 gesto** - UM gesto = UM evento: a repeticao automatica do clique saiu (so com
  `repetir=true`), mas a segunda LEITURA fica, para um botao lento ser visto a reagir. A assinatura do
  efeito passou a incluir `aria-expanded`, `hidden`, display/visibility, a altura da pagina e o estado
  dos IRMAOS - o acordeao que so troca classes dentro de um `content-visibility:hidden` deixou de passar
  por "nada mudou". O texto diz que o alvo foi olhado, em vez de convidar a repetir.
- **#21 recarregar sem medir codigo velho** - a recarga desliga a cache HTTP durante o reload e diz
  quantos ficheiros de codigo vieram da cache (pelo `transferSize`), para nunca medir a versao antiga.
- **#6/#9/#13/#24/#38/#39/#45 acoes partilhadas** - `carregar` e `mostrar` existem nas DUAS ferramentas;
  `roteiro` aceita lista JSON E um gesto por linha ('clicar #btn-x', 'escrever #campo | oi',
  'esperar 500'); a acao `esperar` passou a ser valida tambem no JSON; `carregar` com '/contato' resolve
  no servidor do preview e diz a URL FINAL (nao a intencao); um `avaliar` que navega a meio e reportado
  como "o codigo correu e a pagina navegou", com o endereco novo, em vez de erro seco.
- **#18/#19/#27 medir_pintura** - o `ficheiro` resolve contra a raiz do PROJETO
  (`resolver_caminho_arquivo`) e o erro diz o caminho absoluto tentado; as folhas ligadas por ROTA
  ('/css/dock.css') passam a ser encontradas por hipoteses de layout e as que nao existem saem no
  relatorio com os caminhos tentados. Medido no `src/frontend/index.html`: antes carregava 0 folhas,
  agora 10 de 12 (as duas que faltam, /monaco/... e /xterm/..., sao servidas de node_modules).
- **#4 estado_git** - ja estava feito: a mensagem sem repositorio ensina o `criar=True`. Provado com
  uma pasta temporaria.

**O que continua em aberto:** nada do caderno. Os itens #49 e #50 (landing sem texto explicativo;
produto nasce com o conjunto de paginas) nao sao codigo - sao regra de trabalho e vivem nas
preferencias (`landing-saas` e `responsivo`).
