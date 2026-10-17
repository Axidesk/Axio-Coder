(function () {
  const menuBotao = document.getElementById('menu-botao');
  const nav = document.getElementById('nav');

  if (menuBotao && nav) {
    menuBotao.addEventListener('click', function () {
      const aberta = nav.classList.toggle('aberta');
      menuBotao.setAttribute('aria-expanded', String(aberta));
    });
    nav.addEventListener('click', function (evento) {
      if (evento.target.closest('a')) {
        nav.classList.remove('aberta');
        menuBotao.setAttribute('aria-expanded', 'false');
      }
    });
  }

  const semMovimento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const alvos = document.querySelectorAll('[data-animar]');

  if (semMovimento || !('IntersectionObserver' in window)) {
    alvos.forEach(function (el) { el.classList.add('visivel'); });
  } else {
    const observador = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (entrada) {
        if (entrada.isIntersecting) {
          entrada.target.classList.add('visivel');
          observador.unobserve(entrada.target);
        }
      });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.08 });
    alvos.forEach(function (el) { observador.observe(el); });
  }

  const formulario = document.getElementById('form-contato');

  if (formulario) {
    const enviar = document.getElementById('btn-enviar');
    const intencoes = Array.prototype.slice.call(document.querySelectorAll('.intencao'));
    const linhaEmpresa = document.getElementById('linha-empresa');

    function visivel(campo) {
      return !campo.closest('[hidden]');
    }

    function conferir() {
      if (!enviar) return;
      const obrigatorios = Array.prototype.slice
        .call(formulario.querySelectorAll('[data-obrigatorio]'))
        .filter(visivel);
      const tudoCerto = obrigatorios.every(function (campo) {
        const valor = (campo.value || '').trim();
        if (!valor) return false;
        if (campo.type === 'email') return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(valor);
        return valor.length >= 3;
      });
      enviar.disabled = !tudoCerto;
    }

    intencoes.forEach(function (botao) {
      botao.addEventListener('click', function () {
        intencoes.forEach(function (outro) {
          outro.setAttribute('aria-pressed', String(outro === botao));
        });
        if (linhaEmpresa) linhaEmpresa.hidden = botao.dataset.intencao !== 'empresa';
        conferir();
      });
    });

    formulario.addEventListener('input', conferir);
    conferir();

    formulario.addEventListener('submit', function (evento) {
      evento.preventDefault();
      const aviso = document.getElementById('aviso-envio');
      if (aviso) aviso.hidden = false;
    });
  }

  const olho = document.getElementById('btn-olho');
  const senha = document.getElementById('senha');

  if (olho && senha) {
    olho.addEventListener('click', function () {
      const mostrar = senha.type === 'password';
      senha.type = mostrar ? 'text' : 'password';
      olho.setAttribute('aria-pressed', String(mostrar));
      olho.setAttribute('aria-label', mostrar ? 'Ocultar senha' : 'Mostrar senha');
    });
  }
})();
