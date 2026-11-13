/* Asistente flotante (solo administración).
   Pregunta a /admin/asistente sin salir de la página: la ruta responde JSON cuando llega la cabecera X-Envio: pagina,
   con el mismo orden de siempre (asesor, modelo, consultas directas). La conversación se guarda en la pestaña
   (sessionStorage) para que siga al cambiar de página, y se borra al salir. */
(function () {
  'use strict';
  const raiz = document.getElementById('asistente-flotante');
  if (!raiz) return;
  const $ = (id) => document.getElementById(id);
  const abrir = $('af-abrir'), panel = $('af-panel'), cerrar = $('af-cerrar'), log = $('af-log'), vacio = $('af-vacio'),
    estado = $('af-estado'), aviso = $('af-aviso'), segundos = $('af-segundos'), form = $('af-form'), campo = $('af-pregunta'),
    enviar = $('af-enviar'), cuenta = $('af-cuenta');
  const RUTA = raiz.dataset.ruta || '/admin/asistente';
  const CLAVE = 'asistente-flotante';
  const MAX_MENSAJES = 12;
  const PLAZO_MS = 120000;     // el servidor corta antes (unos 75 s del asesor más el respaldo)
  const AVISO_LARGO_S = 20;

  // ---------- memoria de la pestaña ----------
  function leer() {
    try {
      const d = JSON.parse(sessionStorage.getItem(CLAVE) || 'null');
      if (d && Array.isArray(d.mensajes)) return d;
    } catch (e) { /* sin almacenamiento: la burbuja funciona igual, solo no recuerda */ }
    return { abierto: false, mensajes: [], cuenta: '' };
  }
  const memoria = leer();
  function guardar() {
    memoria.mensajes = memoria.mensajes.slice(-MAX_MENSAJES);
    try { sessionStorage.setItem(CLAVE, JSON.stringify(memoria)); } catch (e) { /* lleno o bloqueado */ }
  }
  // Una pregunta que esperaba respuesta cuando se cambió de página ya no la recibirá
  memoria.mensajes.forEach((m) => { if (m.pendiente) { m.pendiente = false; m.perdida = true; } });

  // ---------- pintar ----------
  const enlaceSeguro = (href) => typeof href === 'string' && href.startsWith('/') && !href.startsWith('//') && !href.startsWith('/\\');
  function el(etiqueta, clase, texto) {
    const n = document.createElement(etiqueta);
    if (clase) n.className = clase;
    if (texto !== undefined && texto !== null) n.textContent = texto;
    return n;
  }
  function enlace(clase, href, texto) {
    if (!enlaceSeguro(href)) return el('span', clase && clase.replace('azul', ''), texto);
    const a = el('a', clase, texto);
    a.href = href;
    return a;
  }

  function nodoDe(m) {
    if (m.rol === 'yo') {
      const n = el('div', 'af-msj af-yo');
      n.appendChild(el('p', null, m.texto));
      if (m.perdida) n.appendChild(el('p', 'af-nota', 'Sin respuesta: cambiaste de página antes de que terminara.'));
      return n;
    }
    const n = el('div', 'af-msj af-el' + (m.error ? ' af-error' : ''));
    if (m.modo_texto) {
      const fila = el('div', 'af-fila');
      fila.appendChild(el('span', 'chip ' + (m.modo_clase || ''), m.modo_texto));
      if (m.duracion_ms) fila.appendChild(el('span', 'eti', (m.duracion_ms / 1000).toFixed(1).replace('.', ',') + ' s'));
      n.appendChild(fila);
    }
    n.appendChild(el('p', 'af-texto', m.texto));
    if (m.salida) n.appendChild(enlace('af-salida', m.salida.href, m.salida.texto));
    if (Array.isArray(m.fuentes) && m.fuentes.length) {
      const f = el('div', 'af-fuentes');
      f.appendChild(el('span', 'eti', 'Fuentes:'));
      m.fuentes.forEach((x) => f.appendChild(enlace('chip azul', x.enlace, x.codigo)));
      n.appendChild(f);
    }
    return n;
  }
  function alFinal() { log.scrollTop = log.scrollHeight; }
  function agregar(m) {
    memoria.mensajes.push(m);
    guardar();
    vacio.hidden = true;
    log.appendChild(nodoDe(m));
    alFinal();
  }

  // ---------- abrir y cerrar ----------
  function mostrar(abierto, enfocar) {
    panel.hidden = !abierto;
    abrir.setAttribute('aria-expanded', String(abierto));
    raiz.classList.toggle('af-abierto', abierto);
    if (abierto) abrir.classList.remove('af-nuevo');
    memoria.abierto = abierto;
    guardar();
    if (abierto) { alFinal(); if (enfocar) campo.focus(); } else if (enfocar) abrir.focus();
  }
  abrir.addEventListener('click', () => mostrar(panel.hidden, true));
  cerrar.addEventListener('click', () => mostrar(false, true));
  panel.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); mostrar(false, true); } });

  // ---------- preguntar ----------
  let enCurso = false;
  const sesionCerrada = () => ({
    rol: 'el', error: true, texto: 'Tu sesión se cerró. Ingresa de nuevo y repite la pregunta.',
    salida: { href: '/entrar?siguiente=' + encodeURIComponent(location.pathname + location.search), texto: 'Ingresar' },
  });
  const fallo = (motivo) => ({
    rol: 'el', error: true, texto: (motivo || 'No pude responder ahora.') + ' Intenta de nuevo o usa la página completa.',
    salida: { href: RUTA, texto: 'Abrir el asistente completo' },
  });

  async function preguntar(pregunta) {
    if (enCurso) return;
    enCurso = true;
    const mia = { rol: 'yo', texto: pregunta, pendiente: true };
    agregar(mia);
    campo.value = '';
    enviar.disabled = true;
    estado.hidden = false;
    aviso.textContent = 'Pensando…';
    const inicio = Date.now();
    const reloj = setInterval(() => {
      const s = Math.round((Date.now() - inicio) / 1000);
      segundos.textContent = s + ' s';
      if (s === AVISO_LARGO_S) aviso.textContent = 'El asesor está consultando los datos; puede tardar hasta un minuto.';
    }, 1000);
    const control = new AbortController();
    const corte = setTimeout(() => control.abort(), PLAZO_MS);
    let respuesta;
    try {
      const datos = new FormData();
      datos.append('pregunta', pregunta);
      const r = await fetch(RUTA, { method: 'POST', body: datos, headers: { 'X-Envio': 'pagina' }, credentials: 'same-origin', signal: control.signal });
      const esJson = (r.headers.get('content-type') || '').includes('application/json');
      if (r.status === 401 || r.redirected) respuesta = sesionCerrada();
      else if (!r.ok || !esJson) respuesta = fallo();
      else {
        const d = await r.json();
        respuesta = { rol: 'el', texto: d.texto || '', modo_texto: d.modo_texto || '', modo_clase: d.modo_clase || '',
          duracion_ms: d.duracion_ms || 0, fuentes: Array.isArray(d.fuentes) ? d.fuentes : [] };
        if (d.tope) memoria.cuenta = d.usadas + ' de ' + d.tope + ' preguntas hoy.';
      }
    } catch (e) {
      respuesta = fallo(e && e.name === 'AbortError' ? 'La respuesta tardó demasiado.' : 'No hubo conexión con la plataforma.');
    } finally {
      clearInterval(reloj);
      clearTimeout(corte);
      estado.hidden = true;
      aviso.textContent = '';
      segundos.textContent = '';
      enviar.disabled = false;
      enCurso = false;
    }
    mia.pendiente = false;
    agregar(respuesta);
    cuenta.textContent = memoria.cuenta || '';
    if (panel.hidden) abrir.classList.add('af-nuevo');
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();   // también evita que el aviso global de «enviando» bloquee el botón
    const pregunta = campo.value.trim();
    if (pregunta) preguntar(pregunta);
  });
  campo.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  raiz.querySelectorAll('[data-pregunta]').forEach((b) => b.addEventListener('click', () => preguntar(b.dataset.pregunta)));
  document.querySelectorAll('form[action="/salir"]').forEach((f) => f.addEventListener('submit', () => {
    try { sessionStorage.removeItem(CLAVE); } catch (e) { /* nada que borrar */ }
  }));

  // ---------- estado inicial ----------
  vacio.hidden = memoria.mensajes.length > 0;
  memoria.mensajes.forEach((m) => log.appendChild(nodoDe(m)));
  cuenta.textContent = memoria.cuenta || '';
  guardar();
  if (memoria.abierto) mostrar(true, false);
}());
