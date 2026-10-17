const reduzirMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const ponteiroFino = window.matchMedia("(pointer: fine)").matches;

function suavizar(valor, alvo, fator) {
  return valor + (alvo - valor) * fator;
}

function iniciarCeu() {
  const tela = document.getElementById("ceu");
  if (!tela) return;

  const gl = tela.getContext("webgl2", { antialias: false, alpha: false, powerPreference: "low-power" })
    || tela.getContext("webgl", { antialias: false, alpha: false });

  if (!gl) {
    document.body.classList.add("sem-webgl");
    return;
  }

  const vsFonte = `#version 300 es
    in vec2 aPos;
    out vec2 vUv;
    void main() {
      vUv = aPos * 0.5 + 0.5;
      gl_Position = vec4(aPos, 0.0, 1.0);
    }`;

  const fsFonte = `#version 300 es
    precision highp float;
    in vec2 vUv;
    out vec4 saida;
    uniform vec2 uRes;
    uniform vec2 uMouse;
    uniform float uTempo;

    float ruido(vec2 p) {
      vec2 i = floor(p);
      vec2 f = fract(p);
      vec2 u = f * f * (3.0 - 2.0 * f);
      float a = fract(sin(dot(i, vec2(127.1, 311.7))) * 43758.5453);
      float b = fract(sin(dot(i + vec2(1.0, 0.0), vec2(127.1, 311.7))) * 43758.5453);
      float c = fract(sin(dot(i + vec2(0.0, 1.0), vec2(127.1, 311.7))) * 43758.5453);
      float d = fract(sin(dot(i + vec2(1.0, 1.0), vec2(127.1, 311.7))) * 43758.5453);
      return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
    }

    float fbm(vec2 p) {
      float v = 0.0;
      float a = 0.5;
      for (int i = 0; i < 5; i++) {
        v += a * ruido(p);
        p *= 2.03;
        a *= 0.5;
      }
      return v;
    }

    void main() {
      vec2 proporcao = vec2(uRes.x / max(uRes.y, 1.0), 1.0);
      vec2 p = (vUv - 0.5) * proporcao;
      float t = uTempo * 0.042;

      vec2 fluxo = vec2(fbm(p * 1.5 + t), fbm(p * 1.5 + vec2(5.2, 1.3) - t));
      float massa = fbm(p * 2.1 + fluxo * 1.7 + vec2(0.0, -t * 1.1));

      vec2 m = (uMouse - 0.5) * proporcao;
      float distancia = length(p - m);
      float halo = smoothstep(0.95, 0.0, distancia);

      vec3 fundo = vec3(0.024, 0.024, 0.043);
      vec3 violeta = vec3(0.486, 0.361, 1.0);
      vec3 ciano = vec3(0.133, 0.827, 0.933);

      float banda = smoothstep(0.32, 0.98, massa);
      vec3 cor = mix(fundo, violeta, banda * 0.82);
      cor = mix(cor, ciano, smoothstep(0.60, 1.0, massa) * 0.5);
      cor += halo * 0.22 * mix(violeta, ciano, 0.45);

      float vinheta = smoothstep(1.45, 0.12, length(p));
      cor *= mix(0.42, 1.0, vinheta);
      cor += (fract(sin(dot(vUv * uRes, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) * 0.016;

      saida = vec4(cor, 1.0);
    }`;

  function compilar(tipo, fonte) {
    const sh = gl.createShader(tipo);
    gl.shaderSource(sh, fonte);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      gl.deleteShader(sh);
      return null;
    }
    return sh;
  }

  const vs = compilar(gl.VERTEX_SHADER, vsFonte);
  const fs = compilar(gl.FRAGMENT_SHADER, fsFonte);
  if (!vs || !fs) {
    document.body.classList.add("sem-webgl");
    return;
  }

  const programa = gl.createProgram();
  gl.attachShader(programa, vs);
  gl.attachShader(programa, fs);
  gl.linkProgram(programa);
  if (!gl.getProgramParameter(programa, gl.LINK_STATUS)) {
    document.body.classList.add("sem-webgl");
    return;
  }
  gl.useProgram(programa);

  const triangulo = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, triangulo);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const posicao = gl.getAttribLocation(programa, "aPos");
  gl.enableVertexAttribArray(posicao);
  gl.vertexAttribPointer(posicao, 2, gl.FLOAT, false, 0, 0);

  const uRes = gl.getUniformLocation(programa, "uRes");
  const uMouse = gl.getUniformLocation(programa, "uMouse");
  const uTempo = gl.getUniformLocation(programa, "uTempo");

  let alvoX = 0.5;
  let alvoY = 0.5;
  let x = 0.5;
  let y = 0.5;
  let escala = 1;

  function ajustar() {
    escala = Math.min(window.devicePixelRatio || 1, 2);
    const largura = Math.floor(tela.clientWidth * escala);
    const altura = Math.floor(tela.clientHeight * escala);
    if (tela.width !== largura || tela.height !== altura) {
      tela.width = largura;
      tela.height = altura;
      gl.viewport(0, 0, largura, altura);
      gl.uniform2f(uRes, largura, altura);
    }
  }

  window.addEventListener("pointermove", (evento) => {
    alvoX = evento.clientX / window.innerWidth;
    alvoY = 1 - evento.clientY / window.innerHeight;
  }, { passive: true });

  window.addEventListener("resize", ajustar, { passive: true });
  ajustar();

  const inicio = performance.now();

  function quadro(agora) {
    x = suavizar(x, alvoX, 0.035);
    y = suavizar(y, alvoY, 0.035);
    gl.uniform2f(uMouse, x, y);
    gl.uniform1f(uTempo, (agora - inicio) / 1000);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (!document.hidden) requestAnimationFrame(quadro);
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) requestAnimationFrame(quadro);
  });

  if (reduzirMovimento) {
    gl.uniform2f(uMouse, 0.5, 0.5);
    gl.uniform1f(uTempo, 12);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  } else {
    requestAnimationFrame(quadro);
  }
}

function iniciarPonteiro() {
  if (!ponteiroFino) return;
  document.body.classList.add("com-ponteiro");

  const cursor = document.querySelector(".curso");
  const brilho = document.getElementById("brilho");
  let alvoX = window.innerWidth / 2;
  let alvoY = window.innerHeight / 2;
  let x = alvoX;
  let y = alvoY;

  window.addEventListener("pointermove", (evento) => {
    alvoX = evento.clientX;
    alvoY = evento.clientY;
    const interativo = evento.target.closest("a, button, [data-tilt], input, textarea, select");
    if (cursor) cursor.classList.toggle("ativo", Boolean(interativo));
  }, { passive: true });

  function quadro() {
    x = suavizar(x, alvoX, 0.18);
    y = suavizar(y, alvoY, 0.18);
    if (cursor) cursor.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    if (brilho) brilho.style.transform = `translate3d(${alvoX}px, ${alvoY}px, 0)`;
    requestAnimationFrame(quadro);
  }

  if (!reduzirMovimento) requestAnimationFrame(quadro);
}

function iniciarTilt() {
  if (!ponteiroFino || reduzirMovimento) return;

  document.querySelectorAll("[data-tilt]").forEach((cartao) => {
    cartao.addEventListener("pointermove", (evento) => {
      const caixa = cartao.getBoundingClientRect();
      const px = (evento.clientX - caixa.left) / caixa.width - 0.5;
      const py = (evento.clientY - caixa.top) / caixa.height - 0.5;
      cartao.style.transform =
        `perspective(900px) rotateY(${px * 9}deg) rotateX(${-py * 9}deg) translateY(-4px)`;
    });

    cartao.addEventListener("pointerleave", () => {
      cartao.style.transform = "";
    });
  });
}

function iniciarMagneticos() {
  if (!ponteiroFino || reduzirMovimento) return;

  document.querySelectorAll("[data-magnetico]").forEach((botao) => {
    botao.addEventListener("pointermove", (evento) => {
      const caixa = botao.getBoundingClientRect();
      const dx = (evento.clientX - caixa.left - caixa.width / 2) * 0.16;
      const dy = (evento.clientY - caixa.top - caixa.height / 2) * 0.22;
      botao.style.transform = `translate(${dx}px, ${dy}px)`;
    });

    botao.addEventListener("pointerleave", () => {
      botao.style.transform = "";
    });
  });
}

function formatarNumero(valor, casas) {
  return valor.toLocaleString("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas
  });
}

function iniciarContadores() {
  const alvos = document.querySelectorAll("[data-contar]");
  if (!alvos.length) return;

  const observador = new IntersectionObserver((entradas) => {
    entradas.forEach((entrada) => {
      if (!entrada.isIntersecting) return;
      const elemento = entrada.target;
      observador.unobserve(elemento);

      const destino = Number.parseFloat(elemento.dataset.contar);
      const casas = Number.parseInt(elemento.dataset.decimal || "0", 10);
      const sufixo = elemento.dataset.sufixo || "";

      if (reduzirMovimento) {
        elemento.textContent = formatarNumero(destino, casas) + sufixo;
        return;
      }

      const inicio = performance.now();
      const duracao = 1400;

      function passo(agora) {
        const progresso = Math.min((agora - inicio) / duracao, 1);
        const alivio = 1 - Math.pow(1 - progresso, 3);
        elemento.textContent = formatarNumero(destino * alivio, casas) + sufixo;
        if (progresso < 1) requestAnimationFrame(passo);
      }

      requestAnimationFrame(passo);
    });
  }, { threshold: 0.4 });

  alvos.forEach((alvo) => {
    alvo.textContent = formatarNumero(0, Number.parseInt(alvo.dataset.decimal || "0", 10)) + (alvo.dataset.sufixo || "");
    observador.observe(alvo);
  });
}

function iniciarJanela() {
  const janela = document.getElementById("janela");
  if (!janela) return;

  const observador = new IntersectionObserver((entradas) => {
    entradas.forEach((entrada) => {
      if (!entrada.isIntersecting) return;
      janela.classList.add("erguida");
      window.setTimeout(() => janela.classList.add("viva"), 140);
      observador.unobserve(janela);
    });
  }, { threshold: 0.25 });

  observador.observe(janela);
}

function iniciarTopo() {
  const topo = document.getElementById("topo");
  if (!topo) return;

  let pedido = false;
  window.addEventListener("scroll", () => {
    if (pedido) return;
    pedido = true;
    requestAnimationFrame(() => {
      topo.classList.toggle("encolhido", window.scrollY > 30);
      pedido = false;
    });
  }, { passive: true });
}

function iniciarFormulario() {
  const contato = document.getElementById("form-contato");
  const entrar = document.getElementById("form-entrar");

  if (contato) {
    const perfis = Array.from(document.querySelectorAll("[data-perfil]"));
    const campos = Array.from(contato.querySelectorAll("[data-para]"));
    const nome = document.getElementById("nome");
    const email = document.getElementById("email");
    const botao = document.getElementById("btn-contato");
    const recado = document.getElementById("recado-contato");
    let perfilAtual = "solo";

    function aplicarPerfil() {
      perfis.forEach((item) => {
        item.classList.toggle("on", item.dataset.perfil === perfilAtual);
      });
      campos.forEach((campo) => {
        campo.hidden = !campo.dataset.para.split(" ").includes(perfilAtual);
      });
    }

    function validar() {
      const emailOk = /\S+@\S+\.\S+/.test(email.value.trim());
      botao.disabled = nome.value.trim().length < 2 || !emailOk;
    }

    perfis.forEach((item) => {
      item.addEventListener("click", () => {
        perfilAtual = item.dataset.perfil;
        aplicarPerfil();
      });
    });

    nome.addEventListener("input", validar);
    email.addEventListener("input", validar);

    contato.addEventListener("submit", (evento) => {
      evento.preventDefault();
      if (botao.disabled) return;
      recado.textContent = "Recebido. Respondemos em até um dia útil.";
      recado.classList.add("visivel");
      botao.textContent = "Enviado";
      botao.disabled = true;
    });

    aplicarPerfil();
    validar();
  }

  if (entrar) {
    const email = document.getElementById("entrar-email");
    const senha = document.getElementById("entrar-senha");
    const botao = document.getElementById("btn-entrar");
    const recado = document.getElementById("recado-entrar");

    function validar() {
      const emailOk = /\S+@\S+\.\S+/.test(email.value.trim());
      botao.disabled = !(emailOk && senha.value.length >= 4);
    }

    email.addEventListener("input", validar);
    senha.addEventListener("input", validar);

    entrar.addEventListener("submit", (evento) => {
      evento.preventDefault();
      if (botao.disabled) return;
      recado.textContent = "Entrando…";
      recado.classList.add("visivel");
    });

    validar();
  }
}

iniciarCeu();
iniciarPonteiro();
iniciarTilt();
iniciarMagneticos();
iniciarContadores();
iniciarJanela();
iniciarTopo();
iniciarFormulario();
