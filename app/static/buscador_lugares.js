// Buscador de origen y destino del formulario de cotización.
// Mientras se escribe sugiere lugares, aeropuertos y países: primero los datos locales (al instante) y, tras una
// pausa con al menos 3 letras, también los de Google. Al elegir, dibuja las casillas de los aeropuertos a comparar.
// Sin dependencias. Si el script no carga, el campo sigue aceptando una ciudad o un código como antes.
(function () {
  'use strict';
  var ESPERA_LOCAL = 200, ESPERA_GOOGLE = 400, LETRAS_GOOGLE = 3;
  var carretera = {factor: 1.3, velocidad_kmh: 70};   // la ruta trae las reglas vigentes

  function nodo(etiqueta, clase, texto) {
    var e = document.createElement(etiqueta);
    if (clase) e.className = clase;
    if (texto != null) e.textContent = texto;
    return e;
  }

  function distanciaKm(lat1, lon1, lat2, lon2) {
    var r = Math.PI / 180, dLat = (lat2 - lat1) * r, dLon = (lon2 - lon1) * r;
    var h = Math.pow(Math.sin(dLat / 2), 2) + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.pow(Math.sin(dLon / 2), 2);
    return 6371 * 2 * Math.asin(Math.sqrt(Math.min(h, 1)));
  }

  function textoHoras(h) {
    if (h == null) return '';
    return h < 1 ? 'menos de 1 h por carretera' : 'unas ' + Math.round(h) + ' h por carretera';
  }

  function textoKm(a) {
    if (a.km == null) return '';
    return a.km < 1 ? 'en el lugar' : Math.round(a.km) + ' km';
  }

  function donde(r) {
    var partes = [];
    if (r.tipo === 'aeropuerto') partes.push('Aeropuerto ' + r.id);
    if (r.tipo === 'pais') partes.push('País: se proponen sus aeropuertos principales');
    if (r.region) partes.push(r.region);
    if (r.pais && r.tipo !== 'pais') partes.push(r.pais);
    return partes.join(' · ');
  }

  function nombreVisible(r) {
    if (r.tipo === 'aeropuerto') return r.nombre + ' (' + r.id + ')';
    if (r.tipo === 'pais' || r.origen === 'google') return r.nombre;
    return [r.nombre, r.region, r.pais].filter(Boolean).join(', ');
  }

  // Lista de sugerencias con el patrón «combobox» de ARIA: flechas para moverse, Enter para elegir, Escape para cerrar.
  // Enter nunca envía el formulario mientras haya sugerencias en camino o a la vista: si la lista aún no llegó, se elige
  // la primera en cuanto llegue. Con `siempreEnter` (campo de agregar aeropuerto), Enter no envía el formulario nunca.
  function Combo(entrada, alElegir, alEscribir, opciones) {
    opciones = opciones || {};
    var lista = nodo('ul');
    lista.id = entrada.id + '-lista';
    lista.setAttribute('role', 'listbox');
    lista.hidden = true;
    entrada.setAttribute('aria-controls', lista.id);
    entrada.insertAdjacentElement('afterend', lista);
    var resultados = [], activo = -1, pedidas = 0, pintada = 0, tLocal = null, tGoogle = null;
    var pendiente = false, elegirAlLlegar = false;

    function cerrar() {
      lista.hidden = true;
      entrada.setAttribute('aria-expanded', 'false');
      entrada.removeAttribute('aria-activedescendant');
      activo = -1;
    }

    function marcar(i) {
      var opciones = lista.querySelectorAll('[role=option]');
      opciones.forEach(function (o, j) { o.setAttribute('aria-selected', j === i ? 'true' : 'false'); });
      activo = i;
      if (i >= 0 && opciones[i]) {
        entrada.setAttribute('aria-activedescendant', opciones[i].id);
        opciones[i].scrollIntoView({block: 'nearest'});
      } else {
        entrada.removeAttribute('aria-activedescendant');
      }
    }

    function elegir(i) {
      var r = resultados[i];
      if (!r) return;
      cerrar();
      alElegir(r);
    }

    function pintar(datos, aviso) {
      resultados = datos;
      lista.textContent = '';
      datos.forEach(function (r, i) {
        var li = nodo('li');
        li.id = lista.id + '-' + i;
        li.setAttribute('role', 'option');
        li.setAttribute('aria-selected', 'false');
        var titulo = nodo('div', 'lugar-nombre', r.nombre);
        if (r.tambien) titulo.appendChild(nodo('span', 'lugar-donde', ' · ' + r.tambien));
        if (r.origen === 'google') { titulo.appendChild(document.createTextNode(' ')); titulo.appendChild(nodo('span', 'chip', 'Google')); }
        li.appendChild(titulo);
        var d = donde(r);
        if (d) li.appendChild(nodo('div', 'lugar-donde', d));
        if (r.tipo === 'lugar' && r.aeropuertos.length) {
          li.appendChild(nodo('div', 'lugar-aeros', 'Aeropuertos: ' + r.aeropuertos.map(function (a) {
            return a.iata + (a.km != null ? ' ' + textoKm(a) : '');
          }).join(', ')));
        } else if (r.aviso) {
          li.appendChild(nodo('div', 'lugar-aeros', r.aviso));
        }
        li.addEventListener('mousedown', function (e) { e.preventDefault(); });   // no quita el foco del campo
        li.addEventListener('click', function () { elegir(i); });
        lista.appendChild(li);
      });
      if (!datos.length) lista.appendChild(nodo('li', 'pie', 'Sin coincidencias. Prueba con otro nombre o con el código del aeropuerto.'));
      if (aviso) lista.appendChild(nodo('li', 'pie', aviso));
      lista.hidden = false;
      entrada.setAttribute('aria-expanded', 'true');
      marcar(-1);
    }

    function pedir(q, google) {
      var n = ++pedidas;
      fetch('/lugares/buscar?limite=8&q=' + encodeURIComponent(q) + (google ? '&google=1' : ''),
            {credentials: 'same-origin', headers: {Accept: 'application/json'}})
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          // Una respuesta vieja o de un texto que ya cambió no pisa la lista actual
          if (!d || n < pintada || entrada.value.trim() !== q) return;
          pintada = n;
          pendiente = false;
          if (d.carretera) carretera = d.carretera;
          pintar(d.resultados || [], d.aviso_google);
          if (elegirAlLlegar) { elegirAlLlegar = false; if (resultados.length) elegir(0); }
        })
        .catch(function () { pendiente = false; elegirAlLlegar = false; /* sin red: el campo sigue aceptando texto libre */ });
    }

    entrada.addEventListener('input', function () {
      if (alEscribir) alEscribir();
      clearTimeout(tLocal);
      clearTimeout(tGoogle);
      var q = entrada.value.trim();
      elegirAlLlegar = false;
      pendiente = q.length >= 2;
      if (q.length < 2) { cerrar(); return; }
      tLocal = setTimeout(function () { pedir(q, false); }, ESPERA_LOCAL);
      if (q.length >= LETRAS_GOOGLE) tGoogle = setTimeout(function () { pedir(q, true); }, ESPERA_GOOGLE);
    });

    entrada.addEventListener('keydown', function (e) {
      var abierta = !lista.hidden && resultados.length;
      if (e.key === 'ArrowDown' && abierta) { e.preventDefault(); marcar(Math.min(activo + 1, resultados.length - 1)); }
      else if (e.key === 'ArrowUp' && abierta) { e.preventDefault(); marcar(Math.max(activo - 1, 0)); }
      else if (e.key === 'Enter') {
        if (abierta) { e.preventDefault(); elegir(activo >= 0 ? activo : 0); }   // nunca envía el formulario a medias
        else if (pendiente) { e.preventDefault(); elegirAlLlegar = true; }      // la lista aún no llega: se elige al llegar
        else if (!lista.hidden || opciones.siempreEnter) {
          e.preventDefault();
          var q = entrada.value.trim();
          if (opciones.siempreEnter && q.length >= 2) {   // p. ej. «SLC» y Enter con la lista cerrada: se busca y se agrega
            clearTimeout(tLocal); clearTimeout(tGoogle);
            pendiente = true; elegirAlLlegar = true;
            pedir(q, false);
          }
        }
      }
      else if (e.key === 'Escape' && !lista.hidden) { e.preventDefault(); cerrar(); }
    });
    entrada.addEventListener('blur', function () { setTimeout(cerrar, 150); });
  }

  // Un campo de origen o destino: el lugar elegido, las casillas de aeropuertos y un buscador para agregar otros.
  function Lado(caja) {
    var nombre = caja.getAttribute('data-buscador');
    var entrada = caja.querySelector('#' + nombre);
    var ocultoAeros = caja.querySelector('[name=' + nombre + '_aeropuertos]');
    var ocultoLugar = caja.querySelector('[name=' + nombre + '_lugar]');
    var ayuda = caja.querySelector('#' + nombre + '-ayuda');
    var panel = caja.querySelector('.aeros');
    var lugar = null, aeros = [];

    function actualizar() {
      var marcados = Array.prototype.slice.call(panel.querySelectorAll('input[type=checkbox]:checked')).map(function (c) { return c.value; });
      ocultoAeros.value = marcados.join(',');
      ayuda.textContent = panel.hidden ? '' : (marcados.length
        ? 'Se comparan ' + marcados.length + (marcados.length === 1 ? ' aeropuerto' : ' aeropuertos') + ' en una sola búsqueda.'
        : 'Marca al menos un aeropuerto.');
    }

    function dibujar(aviso) {
      panel.textContent = '';
      panel.appendChild(nodo('div', 'eti', 'Aeropuertos a comparar'));
      if (aviso) panel.appendChild(nodo('p', 'nota aviso', aviso));
      aeros.forEach(function (a) {
        var etiqueta = nodo('label');
        var casilla = nodo('input');
        casilla.type = 'checkbox';
        casilla.value = a.iata;
        casilla.checked = a.marcado !== false;
        casilla.addEventListener('change', function () { a.marcado = casilla.checked; actualizar(); });
        etiqueta.appendChild(casilla);
        var texto = nodo('span');
        texto.appendChild(nodo('b', null, a.iata));
        texto.appendChild(document.createTextNode(' ' + (a.nombre || '')));
        var detalle = [textoKm(a), textoHoras(a.horas)].filter(Boolean).join(', ');
        if (detalle) texto.appendChild(nodo('span', 'eti', ' — ' + detalle));
        if (a.grande) { texto.appendChild(document.createTextNode(' ')); texto.appendChild(nodo('span', 'chip azul', 'grande')); }
        if (a.origen === 'google') { texto.appendChild(document.createTextNode(' ')); texto.appendChild(nodo('span', 'chip', 'Google')); }
        etiqueta.appendChild(texto);
        panel.appendChild(etiqueta);
      });
      var otro = nodo('div', 'buscador agregar');
      var etiqueta = nodo('label', null, 'Agregar otro aeropuerto (nombre o código)');
      var campo = nodo('input');
      campo.id = nombre + '-agregar';
      campo.name = nombre + '_agregar';   // si el formulario se envía con texto aquí, el servidor no cotiza
      etiqueta.htmlFor = campo.id;
      campo.setAttribute('autocomplete', 'off');
      campo.setAttribute('role', 'combobox');
      campo.setAttribute('aria-autocomplete', 'list');
      campo.setAttribute('aria-expanded', 'false');
      otro.appendChild(etiqueta);
      otro.appendChild(campo);
      panel.appendChild(otro);
      Combo(campo, agregar, null, {siempreEnter: true});
      panel.hidden = false;
      actualizar();
    }

    function agregar(r) {
      r.aeropuertos.forEach(function (a) {
        if (aeros.some(function (x) { return x.iata === a.iata; })) return;
        // La distancia de lo agregado se mide al lugar elegido, cuando hay lugar y coordenadas
        var nuevo = Object.assign({origen: r.origen}, a, {km: null, horas: null});
        if (lugar && r.tipo === 'aeropuerto' && r.lat != null) {
          nuevo.km = distanciaKm(lugar.lat, lugar.lon, r.lat, r.lon);
          nuevo.horas = nuevo.km * carretera.factor / carretera.velocidad_kmh;
        }
        aeros.push(nuevo);
      });
      dibujar();
      var campo = panel.querySelector('#' + nombre + '-agregar');
      if (campo) campo.focus();
    }

    function elegir(r) {
      entrada.value = nombreVisible(r);
      lugar = (r.tipo === 'lugar' && r.lat != null)
        ? {nombre: r.nombre, region: r.region || '', pais: r.pais || '', lat: r.lat, lon: r.lon} : null;
      ocultoLugar.value = lugar ? JSON.stringify(lugar) : '';
      aeros = r.aeropuertos.map(function (a) { return Object.assign({origen: r.origen}, a); });
      dibujar(aeros.length ? null : (r.aviso || 'Sin aeropuertos propuestos. Agrega uno por nombre o código.'));
    }

    function olvidar() {
      // Al volver a escribir, lo elegido antes ya no vale: el campo vuelve a ser texto libre
      lugar = null;
      aeros = [];
      ocultoAeros.value = '';
      ocultoLugar.value = '';
      panel.hidden = true;
      panel.textContent = '';
      ayuda.textContent = '';
    }

    Combo(entrada, elegir, olvidar);
    return {
      valido: function () {
        var aMedias = panel.querySelector('#' + nombre + '-agregar');
        if (aMedias && aMedias.value.trim()) {
          ayuda.textContent = 'Termina de agregar el aeropuerto (elígelo de la lista) o borra ese texto.';
          return false;
        }
        return panel.hidden || ocultoAeros.value !== '';
      },
      campo: entrada,
    };
  }

  var lados = Array.prototype.map.call(document.querySelectorAll('[data-buscador]'), Lado);
  var formulario = lados.length ? lados[0].campo.form : null;
  if (formulario) {
    formulario.addEventListener('submit', function (e) {
      var malo = lados.filter(function (l) { return !l.valido(); })[0];
      if (malo) { e.preventDefault(); malo.campo.focus(); }
    });
  }
})();
