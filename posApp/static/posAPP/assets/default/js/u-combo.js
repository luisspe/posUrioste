/*
 * Selector con búsqueda para todos los <select> de una opción del sistema: se escribe para filtrar las opciones
 * (sin importar acentos ni espacios) y se elige con el mouse, el dedo o el teclado.
 * El <select> original se queda escondido y sigue siendo el que manda el formulario, así que los filtros,
 * el evento "change", .val() de jQuery y el envío funcionan igual que antes.
 * Para dejar un select como el del navegador, ponle data-no-combo.
 */
(function() {
    'use strict';
    var contador = 0;
    var MAXIMO_VISIBLES = 80;  // Con miles de clientes, se pintan solo las primeras coincidencias

    function normalizar(texto) {
        return (texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
    }

    function aplica(select) {
        return !select.multiple && !select.dataset.comboListo && !select.hasAttribute('data-no-combo') &&
            !select.classList.contains('select2-hidden-accessible') && !select.closest('[data-no-combo]');
    }

    function crear(select) {
        if (!aplica(select)) return;
        select.dataset.comboListo = '1';
        var id = 'u-combo-' + (++contador);

        var caja = document.createElement('div');
        caja.className = 'u-combo';
        var input = document.createElement('input');
        input.type = 'text';
        // Mismo tamaño que tenía el select (u-input, form-select-sm, etc.)
        input.className = (select.className || '').replace(/\bform-select-(sm|lg)\b/g, 'form-control-$1')
            .replace(/\bform-select\b/g, 'form-control') + ' u-combo__input';
        if (!/\b(u-input|form-control)\b/.test(input.className)) input.className += ' u-input';
        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-expanded', 'false');
        input.setAttribute('aria-controls', id + '-lista');
        input.setAttribute('autocomplete', 'off');
        input.setAttribute('spellcheck', 'false');
        input.id = (select.id || id) + '-buscar';
        var etiqueta = select.closest('label') && select.closest('label').querySelector('span');
        var porId = select.id && document.querySelector('label[for="' + select.id + '"]');
        var nombre = select.getAttribute('aria-label') || (etiqueta && etiqueta.textContent.trim()) ||
            (porId && porId.textContent.trim());
        if (nombre) input.setAttribute('aria-label', nombre);
        if (porId) porId.setAttribute('for', input.id);
        if (select.getAttribute('aria-labelledby')) input.setAttribute('aria-labelledby', select.getAttribute('aria-labelledby'));
        var flecha = document.createElement('span');
        flecha.className = 'material-symbols-rounded u-combo__flecha';
        flecha.setAttribute('aria-hidden', 'true');
        flecha.textContent = 'expand_more';
        var lista = document.createElement('ul');
        lista.className = 'u-combo__lista';
        lista.id = id + '-lista';
        lista.setAttribute('role', 'listbox');
        lista.hidden = true;

        // El campo va antes del select para que la etiqueta que los envuelve le dé el foco a él
        select.parentNode.insertBefore(caja, select);
        caja.appendChild(input);
        caja.appendChild(flecha);
        caja.appendChild(lista);
        caja.appendChild(select);
        select.classList.add('u-combo__nativo');
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');
        // Si el formulario marca el select como obligatorio, el aviso del navegador lleva al campo visible
        select.addEventListener('focus', function() { input.focus(); });
        select.addEventListener('invalid', function() { caja.classList.add('is-invalido'); });

        var opciones = [], visibles = [], activa = -1;

        function leerOpciones() {
            opciones = [];
            Array.prototype.forEach.call(select.options, function(o, i) {
                if (o.disabled && o.value === '') return;  // los "elige uno" vacíos de las plantillas viejas
                var clave = normalizar(o.text);
                opciones.push({indice: i, valor: o.value, texto: o.text, clave: clave, compacta: clave.replace(/\s+/g, ''),
                               deshabilitada: o.disabled});
            });
        }

        function textoElegido() {
            var o = select.options[select.selectedIndex];
            return o && !(o.disabled && o.value === '') ? o.text : '';
        }

        function refrescar() {
            input.disabled = select.disabled;
            caja.classList.toggle('is-deshabilitado', select.disabled);
            if (lista.hidden) input.value = textoElegido();
            if (select.value) caja.classList.remove('is-invalido');
        }
        select._uComboRefrescar = refrescar;

        function pintar(filtro) {
            var clave = normalizar(filtro), compacta = clave.replace(/\s+/g, '');
            // "5pm" encuentra "5 pm" y al revés
            var todas = opciones.filter(function(o) {
                return !clave || o.clave.indexOf(clave) !== -1 || o.compacta.indexOf(compacta) !== -1;
            });
            visibles = todas.slice(0, MAXIMO_VISIBLES);
            lista.innerHTML = '';
            if (!visibles.length) {
                var vacio = document.createElement('li');
                vacio.className = 'u-combo__vacio';
                vacio.textContent = clave ? 'Sin resultados para "' + filtro + '"' : 'No hay opciones';
                lista.appendChild(vacio);
            }
            visibles.forEach(function(o, i) {
                var li = document.createElement('li');
                li.id = id + '-op-' + o.indice;
                li.setAttribute('role', 'option');
                li.className = 'u-combo__opcion' + (o.valor === '' ? ' u-combo__opcion--todos' : '');
                if (o.deshabilitada) li.setAttribute('aria-disabled', 'true');
                li.setAttribute('aria-selected', String(o.indice === select.selectedIndex));
                var inicio = clave ? o.clave.indexOf(clave) : -1;
                if (inicio >= 0) {
                    li.appendChild(document.createTextNode(o.texto.slice(0, inicio)));
                    var marca = document.createElement('mark');
                    marca.textContent = o.texto.slice(inicio, inicio + clave.length);
                    li.appendChild(marca);
                    li.appendChild(document.createTextNode(o.texto.slice(inicio + clave.length)));
                } else {
                    li.textContent = o.texto || ' ';
                }
                li.addEventListener('mousedown', function(e) { e.preventDefault(); elegir(o); });
                li.addEventListener('mousemove', function() { if (activa !== i) marcar(i, false); });
                lista.appendChild(li);
            });
            if (todas.length > visibles.length) {
                var mas = document.createElement('li');
                mas.className = 'u-combo__vacio';
                mas.textContent = 'Hay ' + (todas.length - visibles.length) + ' más. Escribe para encontrarlo.';
                lista.appendChild(mas);
            }
            var elegida = visibles.findIndex(function(o) { return o.indice === select.selectedIndex; });
            marcar(clave ? 0 : Math.max(elegida, 0), true);
        }

        function marcar(i, desplazar) {
            var items = lista.querySelectorAll('.u-combo__opcion');
            if (!items.length) { activa = -1; input.removeAttribute('aria-activedescendant'); return; }
            activa = Math.max(0, Math.min(i, items.length - 1));
            items.forEach(function(li, n) { li.classList.toggle('is-activa', n === activa); });
            input.setAttribute('aria-activedescendant', items[activa].id);
            if (desplazar) items[activa].scrollIntoView({block: 'nearest'});
        }

        function abrir() {
            if (!lista.hidden || select.disabled) return;
            leerOpciones();
            // Si abajo no cabe la lista (por ejemplo, al final de un modal), se abre hacia arriba
            var rect = input.getBoundingClientRect();
            caja.classList.toggle('is-arriba', window.innerHeight - rect.bottom < 240 && rect.top > 260);
            caja.classList.add('is-abierto');
            input.setAttribute('aria-expanded', 'true');
            lista.hidden = false;
            pintar('');
            input.select();
        }

        function cerrar() {
            caja.classList.remove('is-abierto');
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
            lista.hidden = true;
            input.value = textoElegido();
        }

        function elegir(o) {
            if (o.deshabilitada) return;
            var cambio = select.selectedIndex !== o.indice;
            select.selectedIndex = o.indice;
            cerrar();
            caja.classList.remove('is-invalido');
            if (cambio) select.dispatchEvent(new Event('change', {bubbles: true}));
        }

        input.addEventListener('focus', abrir);
        input.addEventListener('click', abrir);
        input.addEventListener('input', function() { abrir(); pintar(input.value); });
        input.addEventListener('blur', cerrar);
        input.addEventListener('keydown', function(e) {
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                if (lista.hidden) return abrir();
                marcar(activa + (e.key === 'ArrowDown' ? 1 : -1), true);
            } else if (e.key === 'Enter') {
                if (!lista.hidden && visibles[activa]) { e.preventDefault(); elegir(visibles[activa]); }
            } else if (e.key === 'Escape') {
                if (!lista.hidden) { e.preventDefault(); e.stopPropagation(); cerrar(); input.select(); }
            } else if (e.key === 'Tab' && !lista.hidden && input.value && visibles[activa] &&
                       normalizar(input.value) !== normalizar(textoElegido())) {
                elegir(visibles[activa]);
            }
        });
        flecha.addEventListener('mousedown', function(e) {
            e.preventDefault();
            if (lista.hidden) input.focus(); else input.blur();
        });
        // Si otro código cambia el select (filtros que se limpian, sugerencias del punto de venta), el campo lo refleja
        select.addEventListener('change', refrescar);

        leerOpciones();
        refrescar();
        var vacia = opciones.find(function(o) { return o.valor === ''; });
        input.placeholder = select.dataset.placeholder || (vacia && vacia.texto) || 'Elige o escribe para buscar';
    }

    function iniciar(raiz) {
        raiz = raiz || document;
        if (raiz.tagName === 'SELECT') return crear(raiz);
        if (raiz.querySelectorAll) raiz.querySelectorAll('select').forEach(crear);
    }
    window.uCombo = iniciar;

    // jQuery .val('x') cambia el select sin avisar; así el campo visible se entera
    function conectarJQuery() {
        var $ = window.jQuery;
        if (!$ || !$.valHooks || !$.valHooks.select || $.valHooks.select._uCombo) return;
        var original = $.valHooks.select.set;
        $.valHooks.select.set = function(elem, value) {
            var resultado = original.call(this, elem, value);
            if (elem._uComboRefrescar) setTimeout(elem._uComboRefrescar);
            return resultado;
        };
        $.valHooks.select._uCombo = true;
    }

    function arrancar() {
        conectarJQuery();
        iniciar(document);
        // Modales y partes de la página que llegan después (por ejemplo, el modal de cliente o de producto)
        var pendiente = false;
        new MutationObserver(function(cambios) {
            if (pendiente) return;
            var hay = cambios.some(function(c) { return c.addedNodes.length; });
            if (!hay) return;
            pendiente = true;
            requestAnimationFrame(function() { pendiente = false; iniciar(document); });
        }).observe(document.body, {childList: true, subtree: true});
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', arrancar);
    } else {
        arrancar();
    }
})();
