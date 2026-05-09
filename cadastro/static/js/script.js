// CPF/CNPJ: campo único com detecção automática (>11 dígitos = CNPJ)
$(document).ready(function() {
    $('#cep').mask('00000-000');
    $('#telefone').mask('(00) 00000-0000');
    $('#rg').mask('00.000.000-0');

    var $doc = $('#documento');
    if ($doc.length) {
        // Máscara dinâmica CPF/CNPJ. A máscara de CPF tem um '9' extra para
        // permitir o 12º dígito sem que o jQuery Mask trave o input antes
        // do onKeyPress conseguir trocar para a máscara de CNPJ.
        var documentoMaskBehavior = function (val) {
            return (val || '').replace(/\D/g, '').length > 11
                ? '00.000.000/0000-00'
                : '000.000.000-009';
        };
        var documentoMaskOpts = {
            onKeyPress: function (val, e, field, options) {
                field.mask(documentoMaskBehavior(val), options);
                handleDocumentInput();
            }
        };
        $doc.mask(documentoMaskBehavior, documentoMaskOpts);
        handleDocumentInput();
    }
});

function applyTipoPessoaUI(kind) {
    var pfOnly = document.querySelectorAll('.pf-only');
    var pjOnly = document.querySelectorAll('.pj-only');
    var labelNome = document.getElementById('labelNome');
    var inputNome = document.getElementById('nome');
    var nomeFantasia = document.getElementById('nomeFantasia');
    var contratoSocial = document.getElementById('contratoSocial');
    var rg = document.getElementById('rg');
    var dataNascimento = document.getElementById('dataNascimento');

    if (kind === 'pj') {
        pfOnly.forEach(function (el) { el.style.display = 'none'; });
        pjOnly.forEach(function (el) {
            el.style.display = el.classList.contains('row') ? 'flex' : 'block';
        });
        if (labelNome) labelNome.innerText = 'RAZÃO SOCIAL *';
        if (inputNome) inputNome.placeholder = 'Digite a Razão Social';
        if (nomeFantasia) nomeFantasia.required = true;
        if (contratoSocial) contratoSocial.required = true;
        if (rg) rg.required = false;
        if (dataNascimento) dataNascimento.required = false;
    } else {
        pfOnly.forEach(function (el) {
            el.style.display = el.classList.contains('row') ? 'flex' : 'block';
        });
        pjOnly.forEach(function (el) { el.style.display = 'none'; });
        if (labelNome) labelNome.innerText = 'NOME COMPLETO *';
        if (inputNome) inputNome.placeholder = 'Digite seu nome completo';
        if (nomeFantasia) nomeFantasia.required = false;
        if (contratoSocial) contratoSocial.required = false;
        if (rg) rg.required = true;
        if (dataNascimento) dataNascimento.required = true;
    }
}

function handleDocumentInput() {
    var input = document.getElementById('documento');
    if (!input) return;
    var cleanValue = (input.value || '').replace(/\D/g, '');
    var typeHidden = document.getElementById('tipoPessoa');

    // Detecta PF/PJ a partir do tamanho. Acima de 11 dígitos é CNPJ.
    var kind = cleanValue.length > 11 ? 'pj' : 'pf';
    var prev = typeHidden ? typeHidden.value : '';
    if (typeHidden) typeHidden.value = kind;
    // Ao voltar para PF, reseta o cache do auto-fill por CNPJ.
    if (prev === 'pj' && kind === 'pf') window._lastCnpjBrasilApi = '';

    applyTipoPessoaUI(kind);

    // Feedback de validação por tamanho.
    if (kind === 'pf') {
        if (cleanValue.length === 11) {
            if (validarCPF(cleanValue)) {
                input.style.borderColor = '#28a745';
                showInputFeedback(input, true, 'CPF válido');
            } else {
                input.style.borderColor = '#dc3545';
                showInputFeedback(input, false, 'CPF inválido');
            }
        } else {
            input.style.borderColor = '#ddd';
            removeInputFeedback(input);
        }
    } else {
        if (cleanValue.length === 14) {
            if (validarCNPJ(cleanValue)) {
                input.style.borderColor = '#28a745';
                showInputFeedback(input, true, 'CNPJ válido');
                buscarDadosCNPJ(cleanValue);
            } else {
                input.style.borderColor = '#dc3545';
                showInputFeedback(input, false, 'CNPJ inválido');
            }
        } else {
            input.style.borderColor = '#ddd';
            removeInputFeedback(input);
            if (cleanValue.length < 14) window._lastCnpjBrasilApi = '';
        }
    }
}

// Funções de Validação e Feedback
function showInputFeedback(input, isSuccess, message) {
    removeInputFeedback(input);
    const feedback = document.createElement('div');
    feedback.className = `small mt-1 ${isSuccess ? 'text-success' : 'text-danger'} feedback-msg`;
    feedback.innerHTML = `<i class="bi bi-${isSuccess ? 'check-circle' : 'exclamation-circle'} me-1"></i>${message}`;
    input.parentNode.appendChild(feedback);
}

function removeInputFeedback(input) {
    const existing = input.parentNode.querySelector('.feedback-msg');
    if (existing) existing.remove();
}

function validarCPF(cpf) {
    cpf = cpf.replace(/[^\d]+/g, '');
    if (cpf == '' || cpf.length != 11 || /^(\d)\1{10}$/.test(cpf)) return false;
    let add = 0;
    for (let i = 0; i < 9; i++) add += parseInt(cpf.charAt(i)) * (10 - i);
    let rev = 11 - (add % 11);
    if (rev == 10 || rev == 11) rev = 0;
    if (rev != parseInt(cpf.charAt(9))) return false;
    add = 0;
    for (let i = 0; i < 10; i++) add += parseInt(cpf.charAt(i)) * (11 - i);
    rev = 11 - (add % 11);
    if (rev == 10 || rev == 11) rev = 0;
    if (rev != parseInt(cpf.charAt(10))) return false;
    return true;
}

/** Retorna true se a pessoa tiver 18 anos completos ou mais (data ISO yyyy-mm-dd). */
function validarIdadeMinima18(dataISO) {
    if (!dataISO || String(dataISO).trim() === '') return false;
    const parts = String(dataISO).split('-');
    if (parts.length !== 3) return false;
    const y = parseInt(parts[0], 10);
    const mo = parseInt(parts[1], 10) - 1;
    const da = parseInt(parts[2], 10);
    const birth = new Date(y, mo, da);
    if (Number.isNaN(birth.getTime())) return false;
    const today = new Date();
    let age = today.getFullYear() - birth.getFullYear();
    const monthDiff = today.getMonth() - birth.getMonth();
    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
        age--;
    }
    return age >= 18;
}

function validarCNPJ(cnpj) {
    cnpj = cnpj.replace(/[^\d]+/g, '');
    if (cnpj == '' || cnpj.length != 14 || /^(\d)\1{13}$/.test(cnpj)) return false;
    let tamanho = cnpj.length - 2;
    let numeros = cnpj.substring(0, tamanho);
    let digitos = cnpj.substring(tamanho);
    let soma = 0;
    let pos = tamanho - 7;
    for (let i = tamanho; i >= 1; i--) {
        soma += numeros.charAt(tamanho - i) * pos--;
        if (pos < 2) pos = 9;
    }
    let resultado = soma % 11 < 2 ? 0 : 11 - (soma % 11);
    if (resultado != digitos.charAt(0)) return false;
    tamanho = tamanho + 1;
    numeros = cnpj.substring(0, tamanho);
    soma = 0;
    pos = tamanho - 7;
    for (let i = tamanho; i >= 1; i--) {
        soma += numeros.charAt(tamanho - i) * pos--;
        if (pos < 2) pos = 9;
    }
    resultado = soma % 11 < 2 ? 0 : 11 - (soma % 11);
    if (resultado != digitos.charAt(1)) return false;
    return true;
}

function buscarDadosCNPJ(cnpj) {
    if (typeof window._lastCnpjBrasilApi === 'undefined') window._lastCnpjBrasilApi = '';
    if (window._lastCnpjBrasilApi === cnpj) return;
    showNotify('Buscando dados da empresa...', 'info');
    fetch(`https://brasilapi.com.br/api/cnpj/v1/${cnpj}`)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.razao_social) {
                window._lastCnpjBrasilApi = cnpj;
                document.getElementById('nome').value = data.razao_social;
                const nomeFantasia = document.getElementById('nomeFantasia');
                if (nomeFantasia) nomeFantasia.value = data.nome_fantasia || data.razao_social;

                // Auto-preencher endereço se disponível
                if (data.cep) {
                    document.getElementById('cep').value = data.cep;
                    $('#cep').trigger('blur'); // Aciona a busca de CEP já existente
                }
                showNotify('Dados da empresa carregados!', 'success');
            }
        })
        .catch(function () { showNotify('Não foi possível carregar os dados do CNPJ automaticamente.', 'warning'); });
}

// File Upload Listener e Drag-and-Drop
document.addEventListener('DOMContentLoaded', function() {
    initFormRuntimeConfig();
    wireOpcionalOpcoesInputs();

    // Data mínima de instalação (configurável no admin)
    const dateInput = document.getElementById('data_instalacao');
    if (dateInput) {
        dateInput.setAttribute('min', getMinInstallDateStr());
    }

    // Data de nascimento: só permite quem já completou 18 anos (max = hoje − 18 anos)
    const dataNasc = document.getElementById('dataNascimento');
    if (dataNasc) {
        const t = new Date();
        const maxBirth = new Date(t.getFullYear() - 18, t.getMonth(), t.getDate());
        const y = maxBirth.getFullYear();
        const m = String(maxBirth.getMonth() + 1).padStart(2, '0');
        const d = String(maxBirth.getDate()).padStart(2, '0');
        dataNasc.setAttribute('max', `${y}-${m}-${d}`);
    }

    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(input => {
        const wrapper = input.closest('.file-upload-wrapper');
        const info = wrapper ? wrapper.querySelector('.file-upload-info') : null;

        // Adicionar suporte a Drag and Drop
        if (wrapper) {
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                wrapper.addEventListener(eventName, preventDefaults, false);
            });

            function preventDefaults(e) {
                e.preventDefault();
                e.stopPropagation();
            }

            ['dragenter', 'dragover'].forEach(eventName => {
                wrapper.addEventListener(eventName, () => wrapper.classList.add('drag-over'), false);
            });

            ['dragleave', 'drop'].forEach(eventName => {
                wrapper.addEventListener(eventName, () => wrapper.classList.remove('drag-over'), false);
            });

            wrapper.addEventListener('drop', handleDrop, false);

            function handleDrop(e) {
                const dt = e.dataTransfer;
                const files = dt.files;
                input.files = files;
                handleFiles(input, files, info, wrapper);
            }
        }

        if (input) {
            input.addEventListener('change', function(e) {
                handleFiles(this, this.files, info, wrapper);
            });
        }
    });
});

function handleFiles(input, files, info, wrapper) {
    if (files && files.length > 0) {
        const file = files[0];
        const fileName = file.name;
        if (info) info.innerText = `Arquivo selecionado: ${fileName}`;
        if (wrapper) {
            wrapper.classList.add('file-selected');
            
            // Preview da imagem
            if (file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    let preview = wrapper.querySelector('.file-preview');
                    if (!preview) {
                        preview = document.createElement('img');
                        preview.className = 'file-preview';
                        wrapper.appendChild(preview);
                    }
                    preview.src = e.target.result;
                    preview.style.display = 'block';
                }
                reader.readAsDataURL(file);
            } else {
                const preview = wrapper.querySelector('.file-preview');
                if (preview) preview.style.display = 'none';
            }
        }
    } else {
        if (info) info.innerText = 'Clique para selecionar o arquivo';
        if (wrapper) {
            wrapper.classList.remove('file-selected');
            const preview = wrapper.querySelector('.file-preview');
            if (preview) preview.style.display = 'none';
        }
    }
}

// CEP Lookup logic
function handleCEPLookup(cepInput) {
    const cep = cepInput.replace(/\D/g, '');
    if (cep.length === 8) {
        fetch(`https://viacep.com.br/ws/${cep}/json/`)
            .then(response => response.json())
            .then(data => {
                if (!data.erro) {
                    document.getElementById('endereco').value = data.logradouro;
                    document.getElementById('bairro').value = data.bairro;
                    
                    // Pre-select UF
                    const ufSelect = document.getElementById('uf');
                    if (ufSelect) {
                        ufSelect.value = data.uf;
                    }
                    
                    // Pre-select city if it matches Maricá or if it's MG
                    const cidadeSelect = document.getElementById('cidade');
                    if (data.localidade.toLowerCase() === 'maricá') {
                        cidadeSelect.value = 'marica';
                    } else if (data.uf === 'MG') {
                        cidadeSelect.value = 'minas_gerais';
                    } else if (data.uf === 'ES') {
                        if (data.localidade.toLowerCase() === 'muqui') cidadeSelect.value = 'muqui';
                        else if (data.localidade.toLowerCase() === 'piúma') cidadeSelect.value = 'piuma';
                        else if (data.localidade.toLowerCase() === 'mimoso do sul') cidadeSelect.value = 'mimoso';
                        else cidadeSelect.value = 'outra';
                    } else if (data.uf === 'RJ') {
                        const loc = data.localidade.toLowerCase();
                        if (loc === 'cabo frio') cidadeSelect.value = 'cabo_frio';
                        else if (loc === 'saquarema') cidadeSelect.value = 'saquarema';
                        else if (loc === 'unamar') cidadeSelect.value = 'unamar';
                        else cidadeSelect.value = 'outra';
                    } else {
                        cidadeSelect.value = 'outra';
                    }
                    handleCityChange();
                    
                    // Se o logradouro foi preenchido, tenta localizar no mapa automaticamente
                    if (data.logradouro) {
                        setTimeout(updateMapPreview, 500);
                    }
                }
            })
            .catch(error => console.error('Erro ao buscar CEP:', error));
    }
}

document.getElementById('cep').addEventListener('blur', function() {
    handleCEPLookup(this.value);
});

document.getElementById('cep').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault(); // Evita submeter o form ao buscar o CEP
        handleCEPLookup(this.value);
    }
});

// ---------------------------------------------------------------------------
// Mapa: apenas Leaflet + OpenStreetMap (geocoding via Nominatim)
// O campo hidden continua id=google_maps_link por compatibilidade com o modelo;
// o valor salvo é permalink do OpenStreetMap (lat/lon).
// ---------------------------------------------------------------------------
let lMap = null;
let lMarker = null;

function osmLocationLink(lat, lng, zoom) {
    zoom = zoom || 18;
    const la = Number(lat).toFixed(6);
    const lo = Number(lng).toFixed(6);
    return `https://www.openstreetmap.org/?mlat=${la}&mlon=${lo}#map=${zoom}/${la}/${lo}`;
}

function syncOsmLinkFromMarker() {
    if (!lMarker) return;
    const pos = lMarker.getLatLng();
    const inp = document.getElementById('google_maps_link');
    if (inp) inp.value = osmLocationLink(pos.lat, pos.lng);
}

function showMapWrapper(visible) {
    const wrap = document.getElementById('mapLeafletWrapper');
    if (wrap) wrap.style.display = visible ? 'block' : 'none';
}

function geocodeNominatim(fullAddress) {
    const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(fullAddress)}&limit=1`;
    return fetch(url, { headers: { 'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5' } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data && data.length > 0) {
                return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
            }
            return null;
        });
}

function initOrUpdateLeafletMap(lat, lng) {
    if (typeof L === 'undefined') {
        showNotify('Biblioteca do mapa não carregou. Recarregue a página.', 'danger');
        return;
    }
    lat = lat != null ? Number(lat) : -22.915;
    lng = lng != null ? Number(lng) : -42.82;
    const el = document.getElementById('interactiveMap');
    if (!el) return;

    if (!lMap) {
        lMap = L.map('interactiveMap').setView([lat, lng], 16);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        }).addTo(lMap);
        lMarker = L.marker([lat, lng], { draggable: true }).addTo(lMap);
        lMarker.on('dragend', syncOsmLinkFromMarker);
    } else {
        lMap.setView([lat, lng], 16);
        lMarker.setLatLng([lat, lng]);
    }
    syncOsmLinkFromMarker();
    setTimeout(function () {
        if (lMap) lMap.invalidateSize();
    }, 120);
}

/** Botão «Localizar pelo endereço»: geocodifica e mostra o mesmo mapa Leaflet. */
function updateMapPreview() {
    const cep = document.getElementById('cep').value;
    const endereco = document.getElementById('endereco').value;
    const bairro = document.getElementById('bairro').value;
    const cidadeSelect = document.getElementById('cidade');
    const cidade = cidadeSelect.options[cidadeSelect.selectedIndex].text;

    if (!endereco || !cep) {
        showNotify('Preencha o CEP e o Endereço para localizar no mapa.', 'warning');
        return;
    }

    showMapWrapper(true);
    const fullAddress = `${endereco}, ${bairro}, ${cidade}, Brazil`;

    geocodeNominatim(fullAddress)
        .then(function (coords) {
            if (coords) {
                initOrUpdateLeafletMap(coords.lat, coords.lon);
                setTimeout(function () {
                    if (lMap) lMap.invalidateSize();
                }, 280);
                showNotify('Localização marcada no mapa!', 'success');
            } else {
                showNotify('Não foi possível localizar este endereço. Tente «Usar minha localização» ou revise o endereço.', 'warning');
            }
        })
        .catch(function () {
            showNotify('Erro ao consultar o geocodificador. Tente novamente.', 'danger');
        });
}

/**
 * Usa a geolocalização do navegador (GPS/Wi‑Fi). Solicita permissão ao usuário.
 * Útil quando o CEP/endereço não geocodifica bem; o marcador continua arrastável.
 */
function useCurrentLocation() {
    if (!navigator.geolocation) {
        showNotify('Este navegador não suporta geolocalização. Use «Localizar pelo endereço».', 'warning');
        return;
    }

    navigator.geolocation.getCurrentPosition(
        function (pos) {
            var lat = pos.coords.latitude;
            var lng = pos.coords.longitude;
            showMapWrapper(true);
            initOrUpdateLeafletMap(lat, lng);
            if (lMap) {
                lMap.setView([lat, lng], 18);
            }
            setTimeout(function () {
                if (lMap) {
                    lMap.invalidateSize();
                }
            }, 280);
            showNotify('Localização obtida. Arraste o marcador azul se precisar ajustar o ponto exato.', 'success');
        },
        function (err) {
            var msg = 'Não foi possível obter sua localização.';
            if (err.code === 1) {
                msg = 'Permissão de localização negada. Permita o acesso nas configurações do site ou use «Localizar pelo endereço».';
            } else if (err.code === 2) {
                msg = 'Posição indisponível. Verifique se o GPS está ativo ou use «Localizar pelo endereço».';
            } else if (err.code === 3) {
                msg = 'Tempo esgotado ao obter a localização. Tente novamente ou use o endereço.';
            }
            showNotify(msg, 'warning');
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 60000 }
    );
}

// Plan Change logic (PLAN_DETAILS_LEGACY = fallback se o banco não estiver populado)
// Opcional = repetidor Mesh em aluguel em todos os planos (texto alinhado ao form_config / BD)
const LEGACY_OPC_MESH = 'Deseja alugar repetidor Mesh por R$ 29,99/mês?';
const LEGACY_OPC_ROTEADOR_ESSENCIAL = 'Deseja alugar roteador Wi-Fi por R$ 10,00/mês?';
const LEGACY_OPC_COMBO_ROTEADOR_MESH =
    'Aluguel opcional — pode marcar um, os dois ou nenhum: roteador Wi-Fi R$ 10,00/mês; repetidor Mesh R$ 29,99/mês.';
/** Filial 7 (Jacone, Saquarema, Araruama, Unamar): no Essencial, UI roteador + Mesh independentes. */
const FILIAL7_COMBO_ESSENCIAL_SLUGS = ['jacone', 'saquarema', 'araruama', 'unamar'];
/** Filial 7 (exceto Maricá etc.): sem plano Prime 700 MEGA — oferta com Turbo 500 MEGA */
const CIDADES_SEM_PLANO_PRIME = ['araruama', 'jacone', 'saquarema', 'unamar'];
const PLAN_DETAILS_LEGACY = {
    muqui_piuma: {
        essencial: {
            name: "📱 Plano Essencial – 100 MEGA",
            desc: "<strong>R$ 59,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 79,99/mês</strong> (após vencimento)<br><br>- Instalação Grátis<br><br>- <strong>Este plano não inclui roteador Wi-Fi</strong> (você pode usar o seu próprio ou alugar por R$ 10,00/mês)<br><br>- Instalação em até 48h<br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_ROTEADOR_ESSENCIAL
        },
        rapido: {
            name: "🚀 Plano Rápido – 300 Mega",
            desc: "<strong>300 Mega • R$ 89,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 109,99/mês</strong> (após vencimento)<br><br>- Suporte Especializado<br>- 100% Fibra Óptica<br>- 🤩 Instalação Grátis<br>- 😍 Super Wi-Fi 5Ghz incluso<br><br>💨 <strong>Velocidade na medida certa para toda a família navegar, assistir e conectar.</strong><br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_MESH
        },
        turbo: {
            name: "⚡️ Plano Turbo – 500 Mega",
            desc: "<strong>500 Mega • R$ 99,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 119,99/mês</strong> (após vencimento)<br><br>- Suporte Especializado<br>- 100% Fibra Óptica<br>- 🤩 Instalação Grátis<br>- 😍 Super Wi-Fi 5Ghz incluso<br><br>🚀 <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_MESH
        },
        "1giga": {
            name: "🚀 Plano 1 GIGA Fibramar",
            desc: "<strong>1 GIGA • R$ 149,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 169,99/mês</strong> (após vencimento)<br><br>- Wi-Fi 6 incluso<br>- 100% Fibra Óptica<br>- 🤩 Instalação Grátis<br><br>⚡️ <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>🔗 Opcional: Repetidor Mesh por apenas R$ 29,99/mês<br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_MESH
        }
    },
    mimoso: {
        essencial: {
            name: "📱 Plano Essencial – 240 MEGA",
            desc: "<strong>R$ 59,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 79,99/mês</strong> (após vencimento)<br><br>- Instalação Grátis<br><br>- <strong>Este plano não inclui roteador Wi-Fi</strong> (você pode usar o seu próprio ou alugar por R$ 10,00/mês)<br><br>- Instalação em até 48h<br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_ROTEADOR_ESSENCIAL
        },
        plano_300: {
            name: "⚡️ Plano 300 Mega",
            desc: "<strong>300 Mega • R$ 69,99/mês</strong><br><br>- 100% Fibra Óptica<br>- 🤩 Instalação Grátis<br>- 😍 Super Wi-Fi incluso<br><br>📄 Possui fidelidade de 12 meses<br><br>💨 <strong>Perfeito para navegar, assistir e usar redes sociais com estabilidade.</strong>",
            opcional: LEGACY_OPC_MESH
        },
        rapido: {
            name: "🚀 Plano Rápido – 400 Mega",
            desc: "<strong>400 Mega • R$ 79,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 99,99/mês</strong> (após vencimento)<br><br>- Suporte Especializado<br>- 100% Fibra Óptica<br>- 🤩 Instalação Grátis<br>- 😍 Super Wi-Fi 5Ghz incluso<br><br>💨 <strong>Velocidade na medida certa para toda a família navegar, assistir e conectar.</strong><br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_MESH
        },
        turbo: {
            name: "⚡️ Plano Turbo – 500 Mega",
            desc: "<strong>500 Mega • R$ 99,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 119,99/mês</strong> (após vencimento)<br><br>- Suporte Especializado<br>- 100% Fibra Óptica<br>- 🤩 Instalação Grátis<br>- 😍 Super Wi-Fi 5Ghz incluso<br><br>🚀 <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_MESH
        },
        ultra: {
            name: "🔥 Plano Ultra + Watch TV, Qualifica e Mediquo – 600 Mega",
            desc: "<strong>600 Mega • R$ 119,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 139,99/mês</strong> (após vencimento)<br><br>- 🤩 Instalação Grátis<br>- 😍 Super Wi-Fi 5Ghz incluso<br><br>🎁 <strong>Benefícios Exclusivos:</strong><br><br>- 📺 <strong>Watch TV</strong>: filmes, séries e canais infantis<br>- 📽️ Paramount+<br>- 🎓 <strong>Qualifica</strong>: +220 cursos on-line com certificado reconhecido pela ABED e Carteirinha do Estudante para meia-entrada<br>- 🩺 <strong>Mediquo</strong>: consultas médicas ilimitadas 24 h<br>- 🔰 McAfee antivírus<br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_MESH
        },
        plano_700: {
            name: "🚀 Plano 700 Mega",
            desc: "<strong>700 Mega • R$ 89,99/mês</strong><br><br>- 100% Fibra Óptica<br>- 🤩 Instalação Grátis<br>- 😍 Super Wi-Fi incluso<br>- 🎓 Qualifica App (Aplicativo de cursos e clube de vantagens)<br><br>📄 Possui fidelidade de 12 meses<br><br>✨ <strong>Mais velocidade e benefícios para quem quer estudar, trabalhar e aproveitar o máximo da internet.</strong>",
            opcional: LEGACY_OPC_MESH
        },
        "1giga": {
            name: "🚀 Plano 1 GIGA Fibramar",
            desc: "<strong>1 GIGA • R$ 149,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 169,99/mês</strong> (após vencimento)<br><br>- Wi-Fi 6 incluso<br>- 100% Fibra Óptica<br>- 🤩 Instalação Grátis<br><br>⚡️ <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>🔗 Opcional: Repetidor Mesh por apenas R$ 29,99/mês<br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_MESH
        }
    },
    default: {
        essencial: {
            name: "📱 Plano Essencial – 240 MEGA",
            desc: "R$ 59,99/mês (pagando até o vencimento)<br>R$ 79,99/mês (após vencimento)<br><br>Este plano não inclui roteador Wi-Fi (você pode usar o seu próprio ou alugar por R$ 10,00/mês)<br><br>Instalação em até 48h<br>Permanência mínima de 12 meses",
            opcional: LEGACY_OPC_ROTEADOR_ESSENCIAL
        },
        rapido: {
            name: "🚀 Plano Rápido - 400 Mega",
            desc: "R$ 79,99/mês* (pagando até o vencimento)<br>R$ 99,99/mês* (após vencimento)<br><br>Suporte Especializado<br>100% Fibra Óptica<br>😍 Super Wi-Fi 5Ghz incluso<br><br>💨Velocidade na medida certa para toda a família navegar, assistir e conectar.<br><br>Permanência mínima de 12 meses",
            opcional: LEGACY_OPC_MESH
        },
        turbo: {
            name: "Plano Turbo - 500 Mega",
            desc: "R$ 99,99/mês* (até o vencimento)<br>R$ 119,99/mês* (após vencimento)<br>Super Wi-Fi 5Ghz incluso",
            opcional: LEGACY_OPC_MESH
        },
        ultra: {
            name: "🔥 Plano Ultra + Watch TV, Qualifica e Mediquo - 600 Mega",
            desc: "R$ 119,99/mês* (pagando até o vencimento)<br>R$ 139,99/mês* (após vencimento)<br>😍 Super Wi-Fi 5Ghz incluso<br><br>🎁 Benefícios Exclusivos:<br><br>📺 Watch TV: filmes, séries e canais infantis<br>📽️ Paramount<br>🎓 Qualifica: +220 cursos on-line com certificado reconhecido pela ABED e Carteirinha do Estudante para meia-entrada<br>🩺 Mediquo: consultas médicas ilimitadas 24 h<br>🔰 McAfee antivírus<br><br>Permanência mínima de 12 meses",
            opcional: LEGACY_OPC_MESH
        },
        prime: {
            name: "⚡️ Plano Prime – 700 MEGA",
            desc: "<strong>R$ 99,99/mês</strong> (pagando até o vencimento)<br><br><strong>R$ 119,99/mês</strong> (após vencimento)<br><br>- Suporte Especializado<br><br>- Cursos Qualifica + Clube de vantagens<br><br>- 100% Fibra Óptica<br><br>- 😍 Super Wi-Fi 5Ghz incluso<br><br>🚀 <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>- Possui fidelidade de 12 meses",
            opcional: LEGACY_OPC_MESH
        },
        "1giga": {
            name: "Plano Novo – 1 GIGA Fibramar Internet ✨",
            desc: "📡 Velocidade: 1 GIGA<br>💰 Valor: R$ 169,99<br>➡️ Promoção: pagando até o vencimento, sai por apenas R$ 149,99<br>📶 Wi-Fi 6 incluso 🚀<br>📄 Contrato de fidelidade: 12 meses<br>🔗 Opcional: Repetidor Mesh por apenas R$ 29,99 mensais",
            opcional: LEGACY_OPC_MESH
        }
    }
};

let planDetails = PLAN_DETAILS_LEGACY;

function initFormRuntimeConfig() {
    const el = document.getElementById('form-config-data');
    let cfg = null;
    if (el) {
        try {
            cfg = JSON.parse(el.textContent);
        } catch (e) {
            cfg = null;
        }
    }
    window.__FORM_CONFIG__ = cfg;
    if (cfg && cfg.planDetails && Object.keys(cfg.planDetails).length) {
        planDetails = cfg.planDetails;
    } else {
        planDetails = PLAN_DETAILS_LEGACY;
    }
}

function getCityCfg(slug) {
    const cfg = window.__FORM_CONFIG__;
    if (!cfg || !cfg.cities) return null;
    for (let i = 0; i < cfg.cities.length; i++) {
        if (cfg.cities[i].slug === slug) return cfg.cities[i];
    }
    return null;
}

function getExcludedPlanCodesForCity(slug) {
    const c = getCityCfg(slug);
    if (c && Array.isArray(c.excludedPlanCodes) && c.excludedPlanCodes.length) {
        return c.excludedPlanCodes;
    }
    if (slug === 'marica') {
        return ['turbo'];
    }
    if (CIDADES_SEM_PLANO_PRIME.indexOf(slug) >= 0) {
        return ['prime'];
    }
    return [];
}

function getPlanGroupForCity(slug) {
    const c = getCityCfg(slug);
    const key = c && c.planGroup ? c.planGroup : 'default';
    const raw = planDetails[key] || planDetails.default || {};
    const exclude = getExcludedPlanCodesForCity(slug);
    if (!exclude.length) {
        return raw;
    }
    const out = {};
    for (const k of Object.keys(raw)) {
        if (exclude.indexOf(k) === -1) {
            out[k] = raw[k];
        }
    }
    return out;
}

function getMinInstallDateStr() {
    let days = 1;
    const cfg = window.__FORM_CONFIG__;
    if (cfg && cfg.app && cfg.app.minInstallDaysAhead != null) {
        days = parseInt(cfg.app.minInstallDaysAhead, 10);
        if (isNaN(days) || days < 1) days = 1;
    }
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() + days);
    return d.toISOString().split('T')[0];
}

function citySkipsDocs(citySlug) {
    const c = getCityCfg(citySlug);
    if (c) return !!c.skipDocs;
    return citySlug === 'marica' || citySlug === 'minas_gerais';
}

function formatMoneyBR(n) {
    return 'R$ ' + Number(n).toFixed(2).replace('.', ',');
}

function getResumoValorInstalacao(citySlug, isFidelidade) {
    const c = getCityCfg(citySlug);
    if (!c) {
        if (citySlug === 'marica') return isFidelidade ? 'R$ 100,00' : 'R$ 460,00';
        return isFidelidade ? 'GRÁTIS' : 'R$ 360,00';
    }
    const ins = c.instalacao;
    if (isFidelidade) {
        if (ins.comFidelGratis) return 'GRÁTIS';
        return formatMoneyBR(ins.valorComFidel);
    }
    return formatMoneyBR(ins.valorSemFidel);
}

/** Texto do admin/fallback: combo roteador + mesh (marcação independente). */
function isComboOpcionalText(labelText) {
    if (!labelText) return false;
    var s = String(labelText).toLowerCase();
    var hasRouter = s.indexOf('roteador') >= 0 || s.indexOf('wi-fi') >= 0 || s.indexOf('wifi') >= 0;
    var hasMesh = s.indexOf('mesh') >= 0 || s.indexOf('repetidor') >= 0;
    if (hasRouter && hasMesh) return true;
    if (s.indexOf('10,00') >= 0 && s.indexOf('29,99') >= 0) return true;
    return false;
}

function isFilial7ComboEssencialCity(slug) {
    return FILIAL7_COMBO_ESSENCIAL_SLUGS.indexOf(slug) >= 0;
}

/** Combo roteador+Mesh (duas caixas): só Essencial nestas cidades (filial 7). */
function shouldUseEssencialFilial7ComboUI(citySlug, planCodigo) {
    return planCodigo === 'essencial' && isFilial7ComboEssencialCity(citySlug);
}

function isRouterOnlyOpcionalText(labelText) {
    if (!labelText) return false;
    if (isComboOpcionalText(labelText)) return false;
    var s = String(labelText).toLowerCase();
    return (s.indexOf('roteador') >= 0 || s.indexOf('wi-fi') >= 0 || s.indexOf('wifi') >= 0)
        && (s.indexOf('10') >= 0 || s.indexOf('10,00') >= 0);
}

/** Define modo da UI (combo | router | mesh) e o texto do rótulo. */
function resolveOpcionalDisplayMode(citySlug, planCodigo, rawOptional) {
    var raw = rawOptional != null ? String(rawOptional).trim() : '';
    if (!raw) {
        return { mode: 'mesh', label: rawOptional };
    }
    if (shouldUseEssencialFilial7ComboUI(citySlug, planCodigo)) {
        return { mode: 'combo', label: LEGACY_OPC_COMBO_ROTEADOR_MESH };
    }
    if (isComboOpcionalText(rawOptional)) {
        return { mode: 'mesh', label: LEGACY_OPC_MESH };
    }
    if (isRouterOnlyOpcionalText(rawOptional)) {
        return { mode: 'router', label: rawOptional };
    }
    return { mode: 'mesh', label: rawOptional };
}

function resetOpcionalInputs() {
    var ids = ['opc_cb_roteador', 'opc_cb_mesh', 'opc_mesh_only', 'opc_router_only'];
    for (var i = 0; i < ids.length; i++) {
        var el = document.getElementById(ids[i]);
        if (el) el.checked = false;
    }
}

function syncOpcionalHiddenFields() {
    var hAr = document.getElementById('hid_aluguel_roteador_wifi');
    var hMesh = document.getElementById('hid_aluguel_repetidor_mesh');
    if (!hAr || !hMesh) return;
    var og = document.getElementById('opcionaisGroup');
    if (!og || og.style.display === 'none') {
        hAr.value = '0';
        hMesh.value = '0';
        return;
    }
    var mode = og.getAttribute('data-mode') || '';
    if (mode === 'combo') {
        var cbr = document.getElementById('opc_cb_roteador');
        var cbm = document.getElementById('opc_cb_mesh');
        hAr.value = (cbr && cbr.checked) ? '1' : '0';
        hMesh.value = (cbm && cbm.checked) ? '1' : '0';
    } else if (mode === 'mesh') {
        var m = document.getElementById('opc_mesh_only');
        hAr.value = '0';
        hMesh.value = (m && m.checked) ? '1' : '0';
    } else if (mode === 'router') {
        var ronly = document.getElementById('opc_router_only');
        hAr.value = (ronly && ronly.checked) ? '1' : '0';
        hMesh.value = '0';
    } else {
        hAr.value = '0';
        hMesh.value = '0';
    }
}

function wireOpcionalOpcoesInputs() {
    ['opc_cb_roteador', 'opc_cb_mesh', 'opc_mesh_only', 'opc_router_only'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', function () {
                syncOpcionalHiddenFields();
            });
        }
    });
}

/** Descrição do plano: aceita HTML ou texto com *negrito* / **negrito** e quebras \n. */
function renderPlanDescriptionHtml(raw) {
    if (raw == null || raw === '') return '';
    var s = String(raw);
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>');
    if (!/<\s*br\s*\/?>/i.test(s) && s.indexOf('\n') >= 0) {
        s = s.replace(/\n/g, '<br>');
    }
    /* Menos “respiro” entre linhas: vários <br> seguidos viram um só */
    s = s.replace(/(?:<br\s*\/?>[\s\u00A0]*){2,}/gi, '<br>');
    return s;
}

function handlePlanChange() {
    const city = document.getElementById('cidade').value;
    const plan = document.getElementById('plano').value;
    const detailsBox = document.getElementById('planDetails');
    const descDiv = document.getElementById('planDescription');
    const opcionalGroup = document.getElementById('opcionaisGroup');
    const opcionalLabel = document.getElementById('opcionalLabel');
    const comboBox = document.getElementById('opcionaisCombo');
    const routerOnlyBox = document.getElementById('opcionaisRouterOnly');
    const meshOnlyBox = document.getElementById('opcionaisMeshOnly');

    const cityPlans = getPlanGroupForCity(city);

    if (plan && cityPlans[plan]) {
        detailsBox.style.display = 'block';
        descDiv.innerHTML = renderPlanDescriptionHtml(cityPlans[plan].desc);
        
        if (cityPlans[plan].opcional) {
            opcionalGroup.style.display = 'block';
            const resolved = resolveOpcionalDisplayMode(city, plan, cityPlans[plan].opcional);
            opcionalLabel.innerText = resolved.label;
            opcionalGroup.setAttribute('data-mode', resolved.mode);
            if (comboBox && meshOnlyBox && routerOnlyBox) {
                comboBox.style.display = resolved.mode === 'combo' ? 'block' : 'none';
                routerOnlyBox.style.display = resolved.mode === 'router' ? 'block' : 'none';
                meshOnlyBox.style.display = resolved.mode === 'mesh' ? 'block' : 'none';
            }
            resetOpcionalInputs();
            syncOpcionalHiddenFields();
        } else {
            opcionalGroup.style.display = 'none';
            opcionalGroup.setAttribute('data-mode', '');
            if (comboBox) comboBox.style.display = 'none';
            if (routerOnlyBox) routerOnlyBox.style.display = 'none';
            if (meshOnlyBox) meshOnlyBox.style.display = 'none';
            resetOpcionalInputs();
            syncOpcionalHiddenFields();
        }
    } else {
        detailsBox.style.display = 'none';
        opcionalGroup.style.display = 'none';
        opcionalGroup.setAttribute('data-mode', '');
        if (comboBox) comboBox.style.display = 'none';
        if (routerOnlyBox) routerOnlyBox.style.display = 'none';
        if (meshOnlyBox) meshOnlyBox.style.display = 'none';
        resetOpcionalInputs();
        syncOpcionalHiddenFields();
    }
}

// Navigation logic
let currentStep = 1;
let isEditingMode = false;

function nextStep(step) {
    const city = document.getElementById('cidade').value;
    
    if (!validateStep(currentStep)) return;

    // Se estiver em modo de edição, pula direto para a revisão
    if (isEditingMode) {
        isEditingMode = false; // Reset flag
        showStep(6);
        return;
    }

    if (step === 4 && citySkipsDocs(city)) {
        showStep(5);
        return;
    }

    showStep(step);
}

function prevStep(step) {
    const city = document.getElementById('cidade').value;
    
    // Se estiver voltando durante uma edição, cancela o modo edição
    isEditingMode = false;

    if (step === 4 && citySkipsDocs(city)) {
        showStep(3);
        return;
    }

    showStep(step);
}

function startEditing(step) {
    isEditingMode = true;
    showStep(step);
}

function showStep(step) {
    const city = document.getElementById('cidade').value;
    const isSpecialCity = citySkipsDocs(city);
    
    // Toggle visual indicators for Step 4 fields based on city
    // (We no longer use .required = true to avoid browser focus errors on hidden inputs)
    const step4Inputs = document.getElementById('step4').querySelectorAll('input[type="file"]');
    step4Inputs.forEach(input => {
        const wrapper = input.closest('.file-upload-wrapper');
        if (isSpecialCity) {
            if (wrapper) wrapper.style.borderColor = '#ddd';
        } else {
            // Visual check handled by validateStep
        }
    });

    document.querySelectorAll('.form-step').forEach(s => s.classList.remove('active'));
    document.getElementById(`step${step}`).classList.add('active');
    
    // Update progress bar
    const totalSteps = 6;
    let progressWidth = (step / totalSteps) * 100;
    
    // Visual adjustment for skipped step in progress bar
    if (isSpecialCity && step >= 5) {
        progressWidth = ((step) / totalSteps) * 100;
    }

    const progress = document.getElementById('progress');
    if (progress) progress.style.width = `${progressWidth}%`;
    
    if (step === 6) {
        populateSummary();
    }
    
    currentStep = step;
    window.scrollTo(0, 0);
}

function populateSummary() {
    const summary = document.getElementById('confirmationSummary');
    const form = document.getElementById('registrationForm');
    const formData = new FormData(form);
    
    let html = '';
    
    const sections = {
        'DADOS CADASTRAIS': { fields: ['documento', 'tipoPessoa', 'nome_razao', 'nome_fantasia', 'rg', 'inscricao_estadual', 'data_nascimento', 'email', 'telefone'], step: 1 },
        'ENDEREÇO': { fields: ['cep', 'cidade', 'bairro', 'endereco', 'google_maps_link', 'referencia'], step: 2 },
        'PLANO E VENCIMENTO': { fields: ['plano', 'fidelidade', 'vencimento'], step: 3 },
        'DOCUMENTOS': { fields: ['levar_termo', 'comprovante_residencia', 'foto_documento_frente', 'foto_documento_verso', 'selfie_documento'], step: 4 },
        'INSTALAÇÃO': { fields: ['pagamento_instalacao', 'data_instalacao', 'periodo_instalacao', 'origem'], step: 5 }
    };

    const labels = {
        documento: 'CPF/CNPJ', tipoPessoa: 'Tipo de Pessoa', nome_razao: 'Nome/Razão Social', 
        nome_fantasia: 'Nome Fantasia', rg: 'RG', 
        inscricao_estadual: 'Inscrição Estadual', data_nascimento: 'Data de Nascimento',
        email: 'E-mail', telefone: 'Telefone', cep: 'CEP', cidade: 'Cidade',
        bairro: 'Bairro', endereco: 'Endereço', google_maps_link: 'Link da localização (mapa)',
        referencia: 'Referência',
        plano: 'Plano', fidelidade: 'Fidelidade', vencimento: 'Dia de Vencimento',
        levar_termo: 'Levar Termo?',
        comprovante_residencia: 'Comprovante de Residência',
        foto_documento_frente: 'Foto Doc. (Frente)',
        foto_documento_verso: 'Foto Doc. (Verso)',
        selfie_documento: 'Selfie com Documento',
        pagamento_instalacao: 'Modo de Pagamento',
        data_instalacao: 'Data Instalação', periodo_instalacao: 'Período', origem: 'Origem'
    };

    const city = formData.get('cidade');
    const isSpecialCity = citySkipsDocs(city);

    const cfgLabels = (window.__FORM_CONFIG__ && window.__FORM_CONFIG__.cityLabels) || {};
    const legacyCityMap = {
        marica: 'Maricá - RJ', muqui: 'Muqui - ES', piuma: 'Piúma - ES',
        mimoso: 'Mimoso do Sul - ES', cabo_frio: 'Cabo Frio - RJ',
        saquarema: 'Saquarema - RJ',
        unamar: 'Unamar - RJ', sao_paulo: 'São Paulo - SP', outra: 'Outra'
    };

    for (const [section, config] of Object.entries(sections)) {
        // Skip DOCUMENTOS section header for special cities
        if (section === 'DOCUMENTOS' && isSpecialCity) continue;

        html += `
            <div class="summary-section-header">
                <span>${section}</span>
                <button type="button" class="btn-edit" onclick="startEditing(${config.step})">Editar</button>
            </div>
        `;
        config.fields.forEach(field => {
            let value = formData.get(field);
            
            // Especial para arquivos
            const fileFields = ['comprovante_residencia', 'foto_documento_frente', 'foto_documento_verso', 'selfie_documento'];
            if (fileFields.includes(field)) {
                const fileInput = document.getElementsByName(field)[0];
                value = (fileInput && fileInput.files && fileInput.files.length > 0) ? `📎 ${fileInput.files[0].name}` : null;
            }

            if (!value && field !== 'levar_termo') return;

            // Especial para links de mapa
            if (field === 'google_maps_link') {
                value = `<a href="${value}" target="_blank" rel="noopener noreferrer" class="text-primary text-decoration-none fw-bold">📍 Abrir no mapa (OpenStreetMap)</a>`;
            }

            // Formatação amigável
            if (field === 'tipoPessoa') value = value === 'pf' ? 'Pessoa Física' : 'Pessoa Jurídica';
            if (field === 'levar_termo') value = value ? 'Sim' : 'Não (Vou anexar comprovante)';
            
            if (field === 'cidade') {
                value = cfgLabels[value] || legacyCityMap[value] || value;
            }
            if (field === 'plano') {
                const cityPlans = getPlanGroupForCity(city);
                value = cityPlans[value] ? cityPlans[value].name : value;
            }
            if (field === 'fidelidade') value = value === 'sim' ? 'Sim (12 meses)' : 'Não';
            if (field === 'periodo_instalacao') value = value === 'manha' ? 'Manhã' : 'Tarde';
            if (field === 'data_instalacao') {
                const parts = value.split('-');
                if (parts.length === 3) value = `${parts[2]}/${parts[1]}/${parts[0]}`;
            }

            html += `
                <div class="summary-item">
                    <span class="summary-label">${labels[field] || field}:</span>
                    <span class="summary-value">${value}</span>
                </div>
            `;
        });
    }

    syncOpcionalHiddenFields();
    const hidArEl = document.getElementById('hid_aluguel_roteador_wifi');
    const hidMeshEl = document.getElementById('hid_aluguel_repetidor_mesh');
    const ogSummary = document.getElementById('opcionaisGroup');
    if (hidArEl && hidMeshEl && ogSummary && ogSummary.style.display !== 'none') {
        const mode = ogSummary.getAttribute('data-mode') || '';
        const arOn = hidArEl.value === '1';
        const meshOn = hidMeshEl.value === '1';
        if (mode === 'combo') {
            html += `
                <div class="summary-item">
                    <span class="summary-label">Roteador Wi-Fi (aluguel):</span>
                    <span class="summary-value">${arOn ? 'Sim' : 'Não'}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">Repetidor Mesh (aluguel):</span>
                    <span class="summary-value">${meshOn ? 'Sim' : 'Não'}</span>
                </div>
            `;
        } else if (mode === 'router') {
            html += `
                <div class="summary-item">
                    <span class="summary-label">Roteador Wi-Fi (aluguel):</span>
                    <span class="summary-value">${arOn ? 'Sim' : 'Não'}</span>
                </div>
            `;
        } else if (mode === 'mesh') {
            html += `
                <div class="summary-item">
                    <span class="summary-label">Repetidor Mesh (aluguel):</span>
                    <span class="summary-value">${meshOn ? 'Sim' : 'Não'}</span>
                </div>
            `;
        }
    }

    // Financeiro
    const isFidelidade = formData.get('fidelidade') === 'sim';
    const price = getResumoValorInstalacao(city, isFidelidade);

    html += `
        <div class="summary-section-header">RESUMO FINANCEIRO</div>
        <div class="summary-item">
            <span class="summary-label">Valor da Instalação:</span>
            <span class="summary-value fw-bold text-success">${price}</span>
        </div>
    `;

    summary.innerHTML = html;
}



// Mapa de campos obrigatórios por step. Levamos em conta cidade/tipo PF-PJ
// e a regra "levar termo" no momento de chamar.
function getRequiredFieldsForStep(step) {
    const city = document.getElementById('cidade')?.value || '';
    const type = document.getElementById('tipoPessoa')?.value || 'pf';
    const levarTermo = document.getElementById('levar_termo')?.checked || false;

    const requiredFields = {
        1: ['documento', 'nome_razao', 'email', 'telefone'],
        2: ['cep', 'cidade', 'uf', 'bairro', 'endereco', 'referencia'],
        3: ['plano', 'vencimento'],
        4: [],
        5: ['data_instalacao', 'periodo_instalacao', 'origem'],
    };

    if (type === 'pf') {
        requiredFields[1].push('rg', 'data_nascimento');
    } else {
        requiredFields[1].push('nome_fantasia');
        if (document.getElementById('contratoSocial')) {
            requiredFields[1].push('contrato_social');
        }
    }

    if (!citySkipsDocs(city)) {
        const c = getCityCfg(city);
        const exigirFotos = c && typeof c.exigirFotos === 'boolean' ? c.exigirFotos : true;
        if (!levarTermo) requiredFields[4].push('comprovante_residencia');
        if (exigirFotos) {
            requiredFields[4].push('foto_documento_frente', 'foto_documento_verso', 'selfie_documento');
        }
    }

    const fidInput = document.querySelector('input[name="fidelidade"]:checked');
    const isFidelidade = fidInput ? fidInput.value === 'sim' : true;
    const c = getCityCfg(city);
    const precisaPag = c ? (c.alwaysShowPagamento || !isFidelidade) : (city === 'marica' || !isFidelidade);
    if (precisaPag) {
        requiredFields[5].push('pagamento_instalacao');
    }

    return requiredFields[step] || [];
}

function getFieldLabel(fieldName, input) {
    // 1) Tenta um <label for="id"> ou <label> dentro do mesmo .form-group / .pf-only / .pj-only
    if (input?.id) {
        const lbl = document.querySelector(`label[for="${input.id}"]`);
        if (lbl) return lbl.innerText.replace('*', '').trim();
    }
    const group = input?.closest('.form-group, .row, .mb-3, .col-md-6, .col-md-12');
    if (group) {
        const lbl = group.querySelector('label');
        if (lbl) return lbl.innerText.replace('*', '').trim();
    }
    return fieldName;
}

function validateField(fieldName) {
    const type = document.getElementById('tipoPessoa')?.value || 'pf';
    const input = document.getElementsByName(fieldName)[0] || document.getElementById(fieldName);
    if (!input) return { valid: true, input: null };

    let valid = input.type === 'file'
        ? !!(input.files && input.files.length > 0)
        : !!(input.value && input.value.trim() !== '');

    let message = null;

    if (valid && fieldName === 'documento') {
        var clean = (input.value || '').replace(/\D/g, '');
        if (type === 'pj') {
            if (clean.length !== 14 || !validarCNPJ(clean)) {
                valid = false;
                if (clean.length > 0 && clean.length < 14) message = 'CNPJ incompleto.';
                else if (clean.length === 14) message = 'CNPJ inválido.';
            }
        } else if (clean.length !== 11 || !validarCPF(clean)) {
            valid = false;
            if (clean.length > 0 && clean.length < 11) message = 'CPF incompleto.';
            else if (clean.length === 11) message = 'CPF inválido.';
        }
    }

    if (valid && fieldName === 'data_nascimento' && type === 'pf') {
        if (!validarIdadeMinima18(input.value)) {
            valid = false;
            message = 'É necessário ter pelo menos 18 anos para realizar o cadastro.';
        }
    }
    if (valid && fieldName === 'data_instalacao') {
        const selectedDate = new Date(input.value + 'T00:00:00');
        const minD = new Date(getMinInstallDateStr() + 'T00:00:00');
        if (selectedDate < minD) {
            valid = false;
            message = 'A data de instalação não atende à antecedência mínima configurada.';
        }
    }

    if (input.type === 'file') {
        const wrapper = input.closest('.file-upload-wrapper');
        if (wrapper) wrapper.style.borderColor = valid ? '#ddd' : 'red';
    } else {
        input.style.borderColor = valid ? '' : 'red';
    }

    return { valid, input, message };
}

// Valida um step. Retorna true/false.
// Em modo silent, não dispara toast (usado quando varremos vários steps).
function validateStep(step, options) {
    options = options || {};
    const fields = getRequiredFieldsForStep(step);
    let valid = true;
    let firstError = null;

    for (const fieldName of fields) {
        const r = validateField(fieldName);
        if (!r.valid) {
            valid = false;
            if (!firstError) firstError = { fieldName, input: r.input, message: r.message };
        }
    }

    if (!valid && !options.silent) {
        if (firstError && firstError.message) {
            showNotify(firstError.message, 'warning');
        } else if (!document.querySelector('.toast.show')) {
            const lbl = firstError ? getFieldLabel(firstError.fieldName, firstError.input) : null;
            showNotify(
                lbl ? `Falta preencher: ${lbl}.` : 'Por favor, preencha todos os campos obrigatórios (*).',
                'warning'
            );
        }
    }
    return valid;
}

// Varre todos os steps e retorna o primeiro problema encontrado.
// { ok: true } se está tudo OK; senão { ok:false, step, fieldName, input, message }.
function findFirstFormError() {
    const steps = [1, 2, 3, 4, 5];
    for (const s of steps) {
        const fields = getRequiredFieldsForStep(s);
        for (const fieldName of fields) {
            const r = validateField(fieldName);
            if (!r.valid) {
                return { ok: false, step: s, fieldName, input: r.input, message: r.message };
            }
        }
    }
    return { ok: true };
}

// Logic for Cities
function handleCityChange() {
    const city = document.getElementById('cidade').value;
    const installationInfo = document.getElementById('installationInfo');
    const termoOption = document.getElementById('termo_option');
    const pagamentoWrapper = document.getElementById('pagamento_instalacao_wrapper');
    const pagamentoSelect = document.getElementById('pagamento_instalacao');
    const ufSelect = document.getElementById('uf');

    const cityCfg = getCityCfg(city);
    if (ufSelect) {
        if (cityCfg && cityCfg.uf) {
            ufSelect.value = cityCfg.uf;
        } else {
            if (['marica', 'cabo_frio', 'saquarema', 'unamar'].includes(city)) ufSelect.value = 'RJ';
            else if (['muqui', 'piuma', 'mimoso'].includes(city)) ufSelect.value = 'ES';
            else if (city === 'minas_gerais') ufSelect.value = 'MG';
            else if (city === 'sao_paulo') ufSelect.value = 'SP';
        }
    }

    // Update Plans list based on city
    updatePlanOptions(city);

    // Show/Hide installation info
    installationInfo.style.display = 'block';
    calculateInstallation();

    const fidInput = document.querySelector('input[name="fidelidade"]:checked');
    const isFidelidade = fidInput ? fidInput.value === 'sim' : true;

    if (city) {
        const sempre = cityCfg ? cityCfg.alwaysShowPagamento : (city === 'marica');
        if (sempre) {
            pagamentoWrapper.style.display = 'block';
            if (isFidelidade && city === 'marica') {
                pagamentoSelect.value = 'pix';
            }
        } else if (isFidelidade) {
            pagamentoWrapper.style.display = 'none';
            pagamentoSelect.value = 'gratis';
        } else {
            pagamentoWrapper.style.display = 'block';
        }
    }

    const canLevarTermo = cityCfg ? !!cityCfg.termoOption : ['cabo_frio', 'saquarema', 'unamar', 'sao_paulo'].includes(city);
    if (termoOption) {
        termoOption.style.display = canLevarTermo ? 'block' : 'none';
    }
    if (!canLevarTermo) {
        const levarTermoInput = document.getElementById('levar_termo');
        if (levarTermoInput) levarTermoInput.checked = false;
        toggleComprovanteUpload();
    }

    // Update Vencimento options
    updateVencimentoOptions(city);
}

function updatePlanOptions(city) {
    const planoSelect = document.getElementById('plano');
    if (!planoSelect) return;
    const currentVal = planoSelect.value;
    planoSelect.innerHTML = '<option value="">Selecione um plano...</option>';

    const cityPlans = getPlanGroupForCity(city);

    for (const [key, plan] of Object.entries(cityPlans)) {
        const opt = document.createElement('option');
        opt.value = key;
        opt.textContent = plan.name;
        planoSelect.appendChild(opt);
    }
    
    if (cityPlans[currentVal]) planoSelect.value = currentVal;
    handlePlanChange();
}

function toggleComprovanteUpload() {
    const levarTermoInput = document.getElementById('levar_termo');
    const isLevarTermo = levarTermoInput ? levarTermoInput.checked : false;
    const uploadWrapper = document.getElementById('comprovante_upload_wrapper');
    const input = document.getElementById('comprovante_residencia');
    
    if (uploadWrapper && input) {
        if (isLevarTermo) {
            uploadWrapper.style.opacity = '0.5';
            uploadWrapper.style.pointerEvents = 'none';
        } else {
            uploadWrapper.style.opacity = '1';
            uploadWrapper.style.pointerEvents = 'auto';
        }
    }
}

function calculateInstallation() {
    const city = document.getElementById('cidade').value;
    const fidInput = document.querySelector('input[name="fidelidade"]:checked');
    if (!fidInput) return;

    const isFidelidade = fidInput.value === 'sim';
    const installPriceSpan = document.getElementById('installPrice');
    const pagamentoWrapper = document.getElementById('pagamento_instalacao_wrapper');
    const pagamentoSelect = document.getElementById('pagamento_instalacao');
    const cCfg = getCityCfg(city);

    if (!city) return;

    const ins = cCfg && cCfg.instalacao ? cCfg.instalacao : null;
    if (ins) {
        if (isFidelidade) {
            if (ins.comFidelGratis) {
                installPriceSpan.innerText = 'GRÁTIS';
            } else {
                installPriceSpan.innerText = formatMoneyBR(ins.valorComFidel);
            }
        } else {
            installPriceSpan.innerText = formatMoneyBR(ins.valorSemFidel);
        }
        const sempre = cCfg.alwaysShowPagamento;
        if (sempre) {
            pagamentoWrapper.style.display = 'block';
        } else if (isFidelidade) {
            pagamentoWrapper.style.display = 'none';
            pagamentoSelect.value = 'gratis';
        } else {
            pagamentoWrapper.style.display = 'block';
        }
        return;
    }

    if (city === 'marica') {
        const price = isFidelidade ? 100 : 460;
        installPriceSpan.innerText = `R$ ${price.toFixed(2).replace('.', ',')}`;
        pagamentoWrapper.style.display = 'block';
    } else {
        const price = isFidelidade ? 0 : 360;
        installPriceSpan.innerText = isFidelidade ? 'GRÁTIS' : `R$ ${price.toFixed(2).replace('.', ',')}`;

        if (isFidelidade) {
            pagamentoWrapper.style.display = 'none';
            pagamentoSelect.value = 'gratis';
        } else {
            pagamentoWrapper.style.display = 'block';
        }
    }
}

function updateVencimentoOptions(city) {
    const vencimentoSelect = document.getElementById('vencimento');
    const vencimentoIdInfo = document.getElementById('vencimentoIdInfo');
    if (!vencimentoSelect) return;
    vencimentoSelect.innerHTML = '<option value="">Selecione o vencimento</option>';
    if (vencimentoIdInfo) vencimentoIdInfo.innerText = '';

    const today = new Date().getDate();
    let options = [];

    const cfg = getCityCfg(city);
    if (cfg && cfg.vencimentoRules && cfg.vencimentoRules.length) {
        for (let r = 0; r < cfg.vencimentoRules.length; r++) {
            const rule = cfg.vencimentoRules[r];
            if (today >= rule.fromDay && today <= rule.toDay) {
                options = rule.options;
                break;
            }
        }
    }

    if (!options.length) {
        if (city === 'marica' || city === 'minas_gerais') {
            if (today >= 2 && today <= 10) {
                options = [{ day: '03', id: '107' }, { day: '06', id: '91' }, { day: '09', id: '106' }];
            } else if (today >= 11 && today <= 20) {
                options = [{ day: '13', id: '105' }, { day: '18', id: '93' }];
            } else {
                options = [{ day: '22', id: '160' }, { day: '26', id: '161' }, { day: '01', id: '159' }];
            }
        } else {
            const days = ['01', '03', '06', '07', '09', '13', '18'];
            options = days.map(d => ({ day: d, id: 'IXC' }));
        }
    }

    options.forEach(opt => {
        const el = document.createElement('option');
        el.value = opt.day;
        el.dataset.id = opt.id;
        el.textContent = `Dia ${opt.day}`;
        vencimentoSelect.appendChild(el);
    });
}

// Form submission
// Remove `required` de inputs que estão dentro de containers display:none
// (ex.: pf-only/pj-only quando o tipo oposto está selecionado, steps inativos),
// para evitar o popup nativo "Este campo é obrigatório" do Chrome quando
// algum reportValidity acidental dispara. Validação real é via JS.
function clearRequiredOnHiddenInputs() {
    const form = document.getElementById('registrationForm');
    if (!form) return;
    form.querySelectorAll('[required]').forEach((el) => {
        // offsetParent === null indica que o elemento (ou um ancestral) é display:none.
        if (el.offsetParent === null) {
            el.dataset.requiredCleared = '1';
            el.removeAttribute('required');
        }
    });
}

document.getElementById('registrationForm').onsubmit = function(e) {
    e.preventDefault();

    syncOpcionalHiddenFields();
    clearRequiredOnHiddenInputs();

    // Varre TODOS os steps para encontrar campos obrigatórios em branco
    // (assim o usuário não fica "preso" no Step 6 sem saber o que falta).
    const result = findFirstFormError();
    if (!result.ok) {
        const lbl = getFieldLabel(result.fieldName, result.input);
        const msg = result.message || `Falta preencher: ${lbl} (passo ${result.step}).`;
        showNotify(msg, 'warning');

        // Leva o usuário até o passo errado, scrolla até o campo e foca.
        if (result.step !== currentStep) {
            showStep(result.step);
        }
        setTimeout(() => {
            try {
                if (result.input && typeof result.input.scrollIntoView === 'function') {
                    result.input.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                if (result.input && typeof result.input.focus === 'function') {
                    result.input.focus({ preventScroll: true });
                }
            } catch (_) { /* ignora */ }
        }, 50);
        return;
    }

    // LGPD — exige consentimento explícito antes de enviar
    // (marcado pela tela inicial #lgpdGate; se chegou aqui sem valor, algo burlou o fluxo)
    const consentInput = document.getElementById('consentimentoLgpd');
    if (!consentInput || consentInput.value !== '1') {
        showNotify('É necessário aceitar a Política de Privacidade para concluir o cadastro.', 'warning');
        return;
    }

    const submitBtn = this.querySelector('button[type="submit"]');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Enviando...';
    }

    const formData = new FormData(this);
    const csrftokenEl = document.querySelector('[name=csrfmiddlewaretoken]');
    const csrftoken = csrftokenEl ? csrftokenEl.value : '';

    // Usa a URL atual para o post
    const postUrl = window.location.href;

    fetch(postUrl, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: formData
    })
    .then(async response => {
        const data = await response.json();
        if (response.ok && data.status === 'success') {
            document.getElementById('registrationForm').style.display = 'none';
            const header = document.querySelector('.form-header');
            if (header) header.style.display = 'none';
            document.getElementById('successMessage').style.display = 'block';
            window.scrollTo(0, 0);
        } else {
            const errorMsg = data.message || 'Erro ao enviar o cadastro.';
            showNotify(errorMsg, 'danger');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerText = 'Enviar Cadastro';
            }
        }
    })
    .catch(error => {
        console.error('Erro na submissão:', error);
        showNotify('Erro de conexão. Verifique se o servidor está rodando ou sua internet.', 'danger');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerText = 'Enviar Cadastro';
        }
    });
};
