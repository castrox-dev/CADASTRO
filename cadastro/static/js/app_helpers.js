/* Helpers de UI compartilhados — disponíveis em qualquer template que estenda base.html.
   Padroniza:
   - feedback de fetch via showNotify (toasts);
   - estado "busy" (spinner + disabled) em botões;
   - parsing seguro de JSON.
*/
(function (window) {
    'use strict';

    function getCsrfToken() {
        var input = document.querySelector('[name=csrfmiddlewaretoken]');
        return input ? input.value : '';
    }

    function setButtonBusy(btn, busy, busyLabel) {
        if (!btn) return;
        if (busy) {
            if (btn.dataset.idle == null) btn.dataset.idle = btn.innerHTML;
            btn.disabled = true;
            btn.setAttribute('aria-busy', 'true');
            var label = busyLabel || 'CARREGANDO...';
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>' + label;
        } else {
            btn.disabled = false;
            btn.removeAttribute('aria-busy');
            if (btn.dataset.idle != null) {
                btn.innerHTML = btn.dataset.idle;
                delete btn.dataset.idle;
            }
        }
    }

    function safeNotify(message, type) {
        if (typeof window.showNotify === 'function' && message) {
            window.showNotify(message, type || 'primary');
        }
    }

    /**
     * Wrapper sobre fetch que:
     * - tenta parsear JSON da resposta;
     * - dispara toast de sucesso/erro (configurável);
     * - chama callbacks `onSuccess` / `onError`.
     *
     * options aceita os mesmos params do fetch nativo, mais:
     *   busyButton:       elemento <button> a marcar como ocupado durante a chamada.
     *   busyLabel:        texto exibido enquanto carrega.
     *   successMessage:   string OU função(data)->string. Default: data.message.
     *   errorMessage:     string OU função(data)->string. Default: data.message.
     *   silentSuccess:    se true, não mostra toast de sucesso.
     *   onSuccess(data):  callback após sucesso.
     *   onError(err,data):callback após erro.
     */
    function fetchJson(url, fetchOpts, options) {
        fetchOpts = fetchOpts || {};
        options = options || {};

        if (!fetchOpts.headers) fetchOpts.headers = {};
        // Adiciona CSRF automaticamente em métodos não-GET
        var method = (fetchOpts.method || 'GET').toUpperCase();
        if (method !== 'GET' && !fetchOpts.headers['X-CSRFToken']) {
            fetchOpts.headers['X-CSRFToken'] = getCsrfToken();
        }

        if (options.busyButton) {
            setButtonBusy(options.busyButton, true, options.busyLabel);
        }

        return fetch(url, fetchOpts)
            .then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    return { response: response, data: data };
                });
            })
            .then(function (result) {
                var data = result.data || {};
                var ok = result.response.ok && data.status !== 'error';

                if (ok) {
                    if (!options.silentSuccess) {
                        var msg = typeof options.successMessage === 'function'
                            ? options.successMessage(data)
                            : (options.successMessage || data.message);
                        safeNotify(msg, 'success');
                    }
                    if (typeof options.onSuccess === 'function') options.onSuccess(data);
                } else {
                    var res = result.response;
                    var httpLine = '';
                    if (!res.ok) {
                        httpLine = 'HTTP ' + res.status + (res.statusText ? ' ' + res.statusText : '');
                    }
                    var fallbackMsg = data.message
                        || (httpLine ? ('Resposta do servidor: ' + httpLine + '.') : 'Falha na operação.');
                    var emsg = typeof options.errorMessage === 'function'
                        ? options.errorMessage(data)
                        : (options.errorMessage || fallbackMsg);
                    safeNotify(emsg, data.status === 'warning' ? 'warning' : 'danger');
                    var errPayload = Object.assign({}, data, { message: emsg });
                    if (typeof options.onError === 'function') options.onError(null, errPayload);
                }
                return result;
            })
            .catch(function (err) {
                console.error('fetchJson:', err);
                var netMsg = 'Falha de rede: não houve resposta válida do servidor (timeout, offline ou URL incorreta).';
                if (err && err.message) {
                    netMsg = 'Falha de rede: ' + err.message;
                }
                safeNotify(options.errorMessage || netMsg, 'danger');
                if (typeof options.onError === 'function') {
                    options.onError(err, { message: netMsg, logs: [] });
                }
                throw err;
            })
            .finally(function () {
                if (options.busyButton) {
                    setButtonBusy(options.busyButton, false);
                }
            });
    }

    window.fetchJson = fetchJson;
    window.setButtonBusy = setButtonBusy;
    window.getCsrfToken = getCsrfToken;
})(window);
