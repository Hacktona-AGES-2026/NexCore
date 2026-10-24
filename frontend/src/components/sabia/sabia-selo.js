/**
 * <sabia-selo> — mascote animado (versão selo do sabiá)
 *
 * Componente web sem dependências. Funciona em HTML puro, React, Vue,
 * Angular, Svelte etc. Basta importar este arquivo uma vez.
 *
 * Animações: piscar, assobiar, agachar, levantar, chacoalhar.
 * Uso rápido:
 *   <sabia-selo tamanho="96" ocioso></sabia-selo>
 *   document.querySelector('sabia-selo').assobiar();
 */

const SILHUETA =
  'M178 71 L157 66 Q146 55 131 57 Q113 59 97 72 Q78 87 56 106 L14 136 L22 146 ' +
  'L62 124 Q82 137 106 134 Q133 130 145 107 Q151 92 152 82 L158 77 Z';

const NOTA =
  '<ellipse cx="0" cy="0" rx="4.5" ry="3.4" transform="rotate(-20)"></ellipse>' +
  '<path class="haste" d="M3.8 -1 V-15 Q10 -12 9.5 -6"></path>';

const PENA = '<path d="M0 -8 Q4.5 0 0 8 Q-4.5 0 0 -8 Z"></path>';

/**
 * Tabela das animações. `alvo` é a parte do desenho cujo fim de animação
 * marca o fim da animação inteira; `duracao` (ms) é usada como reserva
 * caso o navegador não dispare o evento (ex.: elemento escondido).
 */
export const ANIMACOES = Object.freeze({
  piscar:     { canal: 'olho',    alvo: '.olho',          nome: 'sb-piscar',         duracao: 220 },
  assobiar:   { canal: 'acao',    alvo: '.corpo-acao',    nome: 'sb-assobiar',       duracao: 1600 },
  chacoalhar: { canal: 'acao',    alvo: '.corpo-acao',    nome: 'sb-chacoalhar',     duracao: 700 },
  agachar:    { canal: 'postura', alvo: '.corpo-postura', nome: 'sb-agachar-corpo',  duracao: 450 },
  levantar:   { canal: 'postura', alvo: '.corpo-postura', nome: 'sb-levantar-corpo', duracao: 600 },
});

const CSS = `
:host {
  display: inline-block;
  width: var(--sabia-tamanho, 96px);
  aspect-ratio: 1 / 1;
  line-height: 0;
  vertical-align: middle;
  --_cor: var(--sabia-cor, #7A1F2B);
  --_fundo: var(--sabia-fundo, #F6ECEC);
}
:host([hidden]) { display: none; }
svg { display: block; width: 100%; height: 100%; overflow: visible; }

.anel { fill: none; stroke: var(--_cor); stroke-width: 2.5; }
.disco { fill: var(--_cor); }
.claro { fill: var(--_fundo); }
.traco-claro { fill: none; stroke: var(--_fundo); stroke-linecap: round; }
.traco-escuro { fill: none; stroke: var(--_cor); stroke-linecap: round; }
.olho { fill: var(--_cor); }
.nota ellipse, .pena path { fill: var(--_fundo); }
.nota .haste { fill: none; stroke: var(--_fundo); stroke-width: 2; stroke-linecap: round; }

.corpo-postura, .corpo-acao, .pernas, .olho, .nota, .pena { transform-box: fill-box; }
.corpo-postura, .corpo-acao, .pernas { transform-origin: 50% 100%; }
.olho, .nota, .pena { transform-origin: 50% 50%; }
.nota, .pena { opacity: 0; }

/* Postura parada depois de "agachar" (até chamar "levantar") */
:host([postura="agachado"]) .pernas { transform: scaleY(.6); }
:host([postura="agachado"]) .corpo-postura { transform: translateY(9px) scale(1.03, .96); }

/* ---------- Quadros-chave ---------- */
@keyframes sb-respirar {
  0%, 100% { transform: scale(1, 1); }
  50%      { transform: scale(1.01, 1.025); }
}
@keyframes sb-piscar {
  0%, 100% { transform: scaleY(1); }
  40%, 55% { transform: scaleY(.12); }
}
@keyframes sb-olho-feliz {
  0%, 100% { transform: scaleY(1); }
  15%, 85% { transform: scaleY(.45); }
}
@keyframes sb-assobiar {
  0%   { transform: rotate(0deg) scale(1); }
  15%  { transform: rotate(-7deg) scale(1.03); }
  35%  { transform: rotate(-5deg) scale(1.05); }
  55%  { transform: rotate(-7deg) scale(1.03); }
  75%  { transform: rotate(-5deg) scale(1.05); }
  100% { transform: rotate(0deg) scale(1); }
}
@keyframes sb-nota-a {
  0%   { opacity: 0; transform: translate(0, 0) scale(.6); }
  20%  { opacity: 1; transform: translate(-2px, -7px) scale(1); }
  100% { opacity: 0; transform: translate(-8px, -28px) rotate(-12deg) scale(1); }
}
@keyframes sb-nota-b {
  0%   { opacity: 0; transform: translate(0, 0) scale(.6); }
  20%  { opacity: 1; transform: translate(2px, -6px) scale(1); }
  100% { opacity: 0; transform: translate(6px, -26px) rotate(10deg) scale(1); }
}
@keyframes sb-chacoalhar {
  0%   { transform: rotate(0deg); }
  10%  { transform: rotate(7deg); }
  25%  { transform: rotate(-7deg); }
  40%  { transform: rotate(5deg); }
  55%  { transform: rotate(-4deg); }
  70%  { transform: rotate(2.5deg); }
  85%  { transform: rotate(-1deg); }
  100% { transform: rotate(0deg); }
}
@keyframes sb-pena-1 {
  0%   { opacity: 0; transform: translate(0, 0) rotate(0deg); }
  15%  { opacity: 1; }
  100% { opacity: 0; transform: translate(-20px, -14px) rotate(-90deg); }
}
@keyframes sb-pena-2 {
  0%   { opacity: 0; transform: translate(0, 0) rotate(0deg); }
  15%  { opacity: 1; }
  100% { opacity: 0; transform: translate(6px, -22px) rotate(70deg); }
}
@keyframes sb-pena-3 {
  0%   { opacity: 0; transform: translate(0, 0) rotate(0deg); }
  15%  { opacity: 1; }
  100% { opacity: 0; transform: translate(12px, 20px) rotate(120deg); }
}
@keyframes sb-agachar-corpo {
  0%   { transform: none; }
  70%  { transform: translateY(10px) scale(1.05, .94); }
  100% { transform: translateY(9px) scale(1.03, .96); }
}
@keyframes sb-agachar-pernas {
  0%   { transform: scaleY(1); }
  70%  { transform: scaleY(.56); }
  100% { transform: scaleY(.6); }
}
@keyframes sb-levantar-corpo {
  0%   { transform: translateY(9px) scale(1.03, .96); }
  55%  { transform: translateY(-2px) scale(.98, 1.04); }
  80%  { transform: translateY(.5px) scale(1.01, .99); }
  100% { transform: none; }
}
@keyframes sb-levantar-pernas {
  0%   { transform: scaleY(.6); }
  55%  { transform: scaleY(1.08); }
  80%  { transform: scaleY(.98); }
  100% { transform: scaleY(1); }
}

/* ---------- Ligação classe -> animação (a ordem importa) ---------- */
.ocioso .corpo-acao { animation: sb-respirar 3.2s ease-in-out infinite; }

.a-assobiar .corpo-acao { animation: sb-assobiar 1.6s ease-in-out both; }
.a-assobiar .olho       { animation: sb-olho-feliz 1.6s ease-in-out both; }
.a-assobiar .n1 { animation: sb-nota-a 1.1s ease-out .2s both; }
.a-assobiar .n2 { animation: sb-nota-b 1.0s ease-out .5s both; }
.a-assobiar .n3 { animation: sb-nota-a .9s ease-out .7s both; }

.a-chacoalhar .corpo-acao { animation: sb-chacoalhar .7s ease-in-out both; }
.a-chacoalhar .p1 { animation: sb-pena-1 .55s ease-out .10s both; }
.a-chacoalhar .p2 { animation: sb-pena-2 .55s ease-out .15s both; }
.a-chacoalhar .p3 { animation: sb-pena-3 .55s ease-out .12s both; }

.a-agachar .corpo-postura { animation: sb-agachar-corpo .45s cubic-bezier(.5, 0, .3, 1) both; }
.a-agachar .pernas        { animation: sb-agachar-pernas .45s cubic-bezier(.5, 0, .3, 1) both; }

.a-levantar .corpo-postura { animation: sb-levantar-corpo .6s cubic-bezier(.3, 0, .2, 1) both; }
.a-levantar .pernas        { animation: sb-levantar-pernas .6s cubic-bezier(.3, 0, .2, 1) both; }

.a-piscar .olho { animation: sb-piscar .22s ease-in-out both; }

/* Movimento reduzido: as animações terminam na hora, no estado final certo */
@media (prefers-reduced-motion: reduce) {
  .ocioso .corpo-acao { animation: none; }
  svg * { animation-duration: 1ms !important; animation-delay: 0s !important; }
}
:host([movimento-reduzido]) .ocioso .corpo-acao { animation: none; }
:host([movimento-reduzido]) svg * { animation-duration: 1ms !important; animation-delay: 0s !important; }
`;

const SVG = `
<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" part="svg" role="img" aria-label="Sabiá">
  <circle class="anel" part="anel" cx="100" cy="100" r="92"></circle>
  <circle class="disco" part="disco" cx="100" cy="100" r="84"></circle>
  <g transform="translate(100 104) scale(0.72) translate(-96 -104)">
    <path class="traco-claro" stroke-width="5" d="M16 158 Q100 150 188 160"></path>
    <g class="pernas">
      <path class="traco-claro" stroke-width="3.5" d="M98 133 L94 156 M110 132 L112 156"></path>
    </g>
    <g class="corpo-postura">
      <g class="corpo-acao">
        <path class="claro" d="${SILHUETA}"></path>
        <path class="traco-escuro" stroke-width="3" d="M84 94 Q108 88 130 100"></path>
        <circle class="olho" cx="143" cy="69" r="3.6"></circle>
      </g>
      <g transform="translate(166 54)"><g class="nota n1">${NOTA}</g></g>
      <g transform="translate(172 64)"><g class="nota n2">${NOTA}</g></g>
      <g transform="translate(160 46)"><g class="nota n3">${NOTA}</g></g>
      <g transform="translate(70 100)"><g class="pena p1">${PENA}</g></g>
      <g transform="translate(122 62)"><g class="pena p2">${PENA}</g></g>
      <g transform="translate(108 128)"><g class="pena p3">${PENA}</g></g>
    </g>
  </g>
</svg>`;

// Permite importar o arquivo em ambiente de servidor (SSR) sem quebrar.
const Base = typeof HTMLElement !== 'undefined' ? HTMLElement : class {};

export class SabiaSelo extends Base {
  static get observedAttributes() {
    return ['tamanho', 'ocioso', 'rotulo', 'decorativo'];
  }

  constructor() {
    super();
    this._ativos = {};          // canal -> { id, cancelar }
    this._proximoId = 0;
    this._timerPiscar = null;
    const raiz = this.attachShadow({ mode: 'open' });
    raiz.innerHTML = `<style>${CSS}</style>${SVG}`;
    this._svg = raiz.querySelector('svg');
  }

  connectedCallback() {
    this._aplicarAtributos();
    if (this.hasAttribute('ocioso')) this._iniciarOcioso();
  }

  disconnectedCallback() {
    this._pararOcioso();
    Object.values(this._ativos).forEach((a) => a.cancelar());
  }

  attributeChangedCallback(nome) {
    if (!this._svg) return;
    if (nome === 'ocioso') {
      if (this.hasAttribute('ocioso') && this.isConnected) this._iniciarOcioso();
      else this._pararOcioso();
    } else {
      this._aplicarAtributos();
    }
  }

  /** 'em-pe' ou 'agachado' */
  get postura() {
    return this.getAttribute('postura') === 'agachado' ? 'agachado' : 'em-pe';
  }

  /** true enquanto alguma animação estiver rodando */
  get animando() {
    return Object.keys(this._ativos).length > 0;
  }

  piscar()     { return this.play('piscar'); }
  assobiar()   { return this.play('assobiar'); }
  agachar()    { return this.play('agachar'); }
  levantar()   { return this.play('levantar'); }
  chacoalhar() { return this.play('chacoalhar'); }

  /**
   * Toca uma animação. Retorna uma Promise que resolve com
   * { animacao, cancelada } quando ela termina.
   * Animações de canais diferentes (olho, ação, postura) podem rodar juntas;
   * uma nova animação no mesmo canal interrompe a anterior.
   */
  play(nome) {
    const def = ANIMACOES[nome];
    if (!def) {
      return Promise.reject(new Error(
        `sabia-selo: animação desconhecida "${nome}". Use: ${Object.keys(ANIMACOES).join(', ')}.`
      ));
    }
    if (nome === 'agachar' && this.postura === 'agachado') {
      return Promise.resolve({ animacao: nome, cancelada: false });
    }

    if (this._ativos[def.canal]) this._ativos[def.canal].cancelar();

    const svg = this._svg;
    const alvo = svg.querySelector(def.alvo);
    const classe = `a-${nome}`;
    const id = ++this._proximoId;

    return new Promise((resolve) => {
      let terminou = false;
      let reserva = null;

      const finalizar = (cancelada) => {
        if (terminou) return;
        terminou = true;
        alvo.removeEventListener('animationend', aoTerminar);
        clearTimeout(reserva);
        if (!cancelada) {
          if (nome === 'agachar') this.setAttribute('postura', 'agachado');
          if (nome === 'levantar') this.removeAttribute('postura');
        }
        svg.classList.remove(classe);
        if (this._ativos[def.canal] && this._ativos[def.canal].id === id) {
          delete this._ativos[def.canal];
        }
        const detalhe = { animacao: nome, cancelada };
        this.dispatchEvent(new CustomEvent('sabia-fim', { detail: detalhe, bubbles: true, composed: true }));
        resolve(detalhe);
      };

      const aoTerminar = (e) => {
        if (e.target === alvo && e.animationName === def.nome) finalizar(false);
      };

      this._ativos[def.canal] = { id, cancelar: () => finalizar(true) };

      // Reinicia a animação mesmo se a classe já estiver aplicada.
      svg.classList.remove(classe);
      void getComputedStyle(alvo).animationName;
      svg.classList.add(classe);

      alvo.addEventListener('animationend', aoTerminar);
      reserva = setTimeout(() => finalizar(false), def.duracao + 250);

      this.dispatchEvent(new CustomEvent('sabia-inicio', { detail: { animacao: nome }, bubbles: true, composed: true }));
    });
  }

  _aplicarAtributos() {
    const tamanho = this.getAttribute('tamanho');
    if (tamanho) {
      this.style.setProperty('--sabia-tamanho', /^\d+(\.\d+)?$/.test(tamanho) ? `${tamanho}px` : tamanho);
    } else {
      this.style.removeProperty('--sabia-tamanho');
    }
    if (this.hasAttribute('decorativo')) {
      this._svg.setAttribute('aria-hidden', 'true');
      this._svg.removeAttribute('role');
      this._svg.removeAttribute('aria-label');
    } else {
      this._svg.removeAttribute('aria-hidden');
      this._svg.setAttribute('role', 'img');
      this._svg.setAttribute('aria-label', this.getAttribute('rotulo') || 'Sabiá');
    }
  }

  _iniciarOcioso() {
    this._svg.classList.add('ocioso');
    this._pararTimer();
    const agendar = () => {
      this._timerPiscar = setTimeout(() => {
        if (!this._ativos.olho && !this._ativos.acao) {
          this.piscar().then(() => {
            // De vez em quando, uma piscada dupla
            if (Math.random() < 0.25) {
              setTimeout(() => {
                if (this.isConnected && this.hasAttribute('ocioso') && !this._ativos.olho) this.piscar();
              }, 120);
            }
          });
        }
        agendar();
      }, 2500 + Math.random() * 3500);
    };
    agendar();
  }

  _pararOcioso() {
    if (this._svg) this._svg.classList.remove('ocioso');
    this._pararTimer();
  }

  _pararTimer() {
    clearTimeout(this._timerPiscar);
    this._timerPiscar = null;
  }
}

/** Registra o elemento (já é chamado automaticamente com "sabia-selo"). */
export function registrarSabiaSelo(tag = 'sabia-selo') {
  if (typeof customElements !== 'undefined' && !customElements.get(tag)) {
    customElements.define(tag, SabiaSelo);
  }
}

registrarSabiaSelo();
