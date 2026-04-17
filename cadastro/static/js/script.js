// Document Auto-detection logic and Masks
$(document).ready(function() {
    // Inicializar máscaras jQuery Mask
    $('#cep').mask('00000-000');
    $('#telefone').mask('(00) 00000-0000');
    $('#rg').mask('00.000.000-0');
    
    // Máscara dinâmica para CPF/CNPJ
    var options = {
        onKeyPress: function(val, e, field, options) {
            var masks = ['000.000.000-00##', '00.000.000/0000-00'];
            var mask = (val.replace(/\D/g, '').length > 11) ? masks[1] : masks[0];
            $('#documento').mask(mask, options);
            handleDocumentInput(); // Mantém a lógica de troca PF/PJ
        }
    };
    $('#documento').mask('000.000.000-00##', options);
});

function handleDocumentInput() {
    const input = document.getElementById('documento');
    const value = input.value;
    const cleanValue = value.replace(/\D/g, '');
    
    const typeHidden = document.getElementById('tipoPessoa');
    const pfOnly = document.querySelectorAll('.pf-only');
    const pjOnly = document.querySelectorAll('.pj-only');
    const labelNome = document.getElementById('labelNome');
    const inputNome = document.getElementById('nome');
    
    // IDs corretos do form.html
    const nomeFantasia = document.getElementById('nomeFantasia');
    const contratoSocial = document.getElementById('contratoSocial');
    const rg = document.getElementById('rg');
    const dataNascimento = document.getElementById('dataNascimento');

    // Feedback visual de validação
    if (cleanValue.length === 11) {
        if (validarCPF(cleanValue)) {
            input.style.borderColor = '#28a745';
            showInputFeedback(input, true, 'CPF Válido');
        } else {
            input.style.borderColor = '#dc3545';
            showInputFeedback(input, false, 'CPF Inválido');
        }
    } else if (cleanValue.length === 14) {
        if (validarCNPJ(cleanValue)) {
            input.style.borderColor = '#28a745';
            showInputFeedback(input, true, 'CNPJ Válido');
            buscarDadosCNPJ(cleanValue);
        } else {
            input.style.borderColor = '#dc3545';
            showInputFeedback(input, false, 'CNPJ Inválido');
        }
    } else {
        input.style.borderColor = '#ddd';
        removeInputFeedback(input);
    }

    if (cleanValue.length > 11) {
        // Switch to PJ
        typeHidden.value = 'pj';
        pfOnly.forEach(el => el.style.display = 'none');
        pjOnly.forEach(el => {
            el.style.display = el.classList.contains('row') ? 'flex' : 'block';
        });
        labelNome.innerText = 'RAZÃO SOCIAL *';
        inputNome.placeholder = 'Digite a Razão Social';
        if (nomeFantasia) nomeFantasia.required = true;
        if (contratoSocial) contratoSocial.required = true;
        if (rg) rg.required = false;
        if (dataNascimento) dataNascimento.required = false;
    } else {
        // Default to PF
        typeHidden.value = 'pf';
        pfOnly.forEach(el => {
            el.style.display = el.classList.contains('row') ? 'flex' : 'block';
        });
        pjOnly.forEach(el => el.style.display = 'none');
        labelNome.innerText = 'NOME COMPLETO *';
        inputNome.placeholder = 'Digite seu nome completo';
        if (nomeFantasia) nomeFantasia.required = false;
        if (contratoSocial) contratoSocial.required = false;
        if (rg) rg.required = true;
        if (dataNascimento) dataNascimento.required = true;
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
    showNotify('Buscando dados da empresa...', 'info');
    fetch(`https://brasilapi.com.br/api/cnpj/v1/${cnpj}`)
        .then(r => r.json())
        .then(data => {
            if (data.razao_social) {
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
        .catch(() => showNotify('Não foi possível carregar os dados do CNPJ automaticamente.', 'warning'));
}

// File Upload Listener e Drag-and-Drop
document.addEventListener('DOMContentLoaded', function() {
    // Set minimum date for installation (tomorrow)
    const dateInput = document.getElementById('data_instalacao');
    if (dateInput) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        const minDate = tomorrow.toISOString().split('T')[0];
        dateInput.setAttribute('min', minDate);
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
document.getElementById('cep').addEventListener('blur', function() {
    const cep = this.value.replace(/\D/g, '');
    if (cep.length === 8) {
        fetch(`https://viacep.com.br/ws/${cep}/json/`)
            .then(response => response.json())
            .then(data => {
                if (!data.erro) {
                    document.getElementById('endereco').value = data.logradouro;
                    document.getElementById('bairro').value = data.bairro;
                    
                    // Pre-select city if it matches Maricá or if it's MG
                    const cidadeSelect = document.getElementById('cidade');
                    if (data.localidade.toLowerCase() === 'maricá') {
                        cidadeSelect.value = 'marica';
                    } else if (data.uf === 'MG') {
                        cidadeSelect.value = 'minas_gerais';
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
});

// Map Preview logic
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

    const fullAddress = `${endereco}, ${bairro}, ${cidade}, Brazil`;
    const encodedAddress = encodeURIComponent(fullAddress);
    
    // URL para o iframe (Embed)
    const mapUrl = `https://maps.google.com/maps?q=${encodedAddress}&t=&z=15&ie=UTF8&iwloc=&output=embed`;
    
    // URL para o link direto (que será salvo no banco)
    const directLink = `https://www.google.com/maps/search/?api=1&query=${encodedAddress}`;
    
    document.getElementById('mapIframe').src = mapUrl;
    document.getElementById('mapPreviewContainer').style.display = 'block';
    
    // Hide manual map if it's open
    const manualContainer = document.getElementById('manualMapContainer');
    if (manualContainer) manualContainer.style.display = 'none';

    document.getElementById('google_maps_link').value = directLink;
    
    showNotify('Localização marcada no mapa!', 'success');
}

// Plan Change logic
const planDetails = {
    // Muqui e Piúma
    muqui_piuma: {
        essencial: {
            name: "Plano Essencial – 100 MEGA",
            desc: "R$ 59,99/mês (até o vencimento)<br>R$ 79,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Sem roteador incluso",
            opcional: "Deseja alugar roteador Wi-Fi por R$ 10,00/mês?"
        },
        rapido: {
            name: "Plano Rápido – 300 MEGA",
            desc: "R$ 89,99/mês (até o vencimento)<br>R$ 109,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi 5Ghz incluso"
        },
        turbo: {
            name: "Plano Turbo – 500 MEGA",
            desc: "R$ 99,99/mês (até o vencimento)<br>R$ 119,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi 5Ghz incluso"
        },
        "1giga": {
            name: "Plano 1 GIGA Fibramar",
            desc: "R$ 149,99/mês (até o vencimento)<br>R$ 169,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Wi-Fi 6 incluso",
            opcional: "Deseja Repetidor Mesh por apenas R$ 29,99/mês?"
        }
    },
    // Mimoso
    mimoso: {
        essencial: {
            name: "Plano Essencial – 240 MEGA",
            desc: "R$ 59,99/mês (até o vencimento)<br>R$ 79,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Sem roteador incluso",
            opcional: "Deseja alugar roteador Wi-Fi por R$ 10,00/mês?"
        },
        plano_300: {
            name: "Plano 300 Mega",
            desc: "R$ 69,99/mês<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi incluso"
        },
        rapido: {
            name: "Plano Rápido – 400 MEGA",
            desc: "R$ 79,99/mês (até o vencimento)<br>R$ 99,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi 5Ghz incluso"
        },
        turbo: {
            name: "Plano Turbo – 500 MEGA",
            desc: "R$ 99,99/mês (até o vencimento)<br>R$ 119,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi 5Ghz incluso"
        },
        ultra: {
            name: "Plano Ultra – 600 MEGA",
            desc: "R$ 119,99/mês (até o vencimento)<br>R$ 139,99/mês (após vencimento)<br>Watch TV, Paramount+, Qualifica, Mediquo e McAfee inclusos"
        },
        plano_700: {
            name: "Plano 700 Mega",
            desc: "R$ 89,99/mês<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi + Qualifica App incluso"
        },
        "1giga": {
            name: "Plano 1 GIGA Fibramar",
            desc: "R$ 149,99/mês (até o vencimento)<br>R$ 169,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Wi-Fi 6 incluso",
            opcional: "Deseja Repetidor Mesh por apenas R$ 29,99/mês?"
        }
    },
    // Padrão (Maricá e outros)
    default: {
        essencial: {
            name: "Plano Essencial – 240 MEGA",
            desc: "R$ 59,99/mês (até o vencimento)<br>R$ 79,99/mês (após vencimento)<br>Contrato 12 meses",
            opcional: "Deseja alugar roteador Wi-Fi por R$ 10,00/mês?"
        },
        rapido: {
            name: "Plano Rápido - 400 Mega",
            desc: "R$ 79,99/mês* (até o vencimento)<br>R$ 99,99/mês* (após vencimento)<br>Super Wi-Fi 5Ghz incluso"
        },
        turbo: {
            name: "Plano Turbo - 500 Mega",
            desc: "R$ 99,99/mês* (até o vencimento)<br>R$ 119,99/mês* (após vencimento)<br>Super Wi-Fi 5Ghz incluso"
        },
        ultra: {
            name: "Plano Ultra + Benefícios - 600 Mega",
            desc: "R$ 119,99/mês* (até o vencimento)<br>R$ 139,99/mês* (após vencimento)<br>Watch TV, Paramount, Qualifica, Mediquo e McAfee inclusos"
        },
        "1giga": {
            name: "Plano Novo – 1 GIGA",
            desc: "R$ 149,99 (até o vencimento)<br>R$ 169,99 (valor normal)<br>Wi-Fi 6 incluso 🚀",
            opcional: "Deseja Repetidor Mesh por apenas R$ 29,99 mensais?"
        }
    }
};

function handlePlanChange() {
    const city = document.getElementById('cidade').value;
    const plan = document.getElementById('plano').value;
    const detailsBox = document.getElementById('planDetails');
    const descDiv = document.getElementById('planDescription');
    const opcionalGroup = document.getElementById('opcionaisGroup');
    const opcionalLabel = document.getElementById('opcionalLabel');

    let cityPlans = planDetails.default;
    if (city === 'muqui' || city === 'piuma') cityPlans = planDetails.muqui_piuma;
    else if (city === 'mimoso') cityPlans = planDetails.mimoso;

    if (plan && cityPlans[plan]) {
        detailsBox.style.display = 'block';
        descDiv.innerHTML = `<strong>Detalhes do Plano:</strong><br>${cityPlans[plan].desc}`;
        
        if (cityPlans[plan].opcional) {
            opcionalGroup.style.display = 'block';
            opcionalLabel.innerText = cityPlans[plan].opcional;
        } else {
            opcionalGroup.style.display = 'none';
        }
    } else {
        detailsBox.style.display = 'none';
        opcionalGroup.style.display = 'none';
    }
}

// RG Mask and Limit
document.getElementById('rg').addEventListener('input', function(e) {
    let value = e.target.value.replace(/\D/g, '');
    if (value.length > 9) value = value.slice(0, 9); // Limite comum de 9 dígitos
    
    // Máscara simples para RG (00.000.000-0)
    if (value.length > 8) {
        value = value.replace(/(\d{2})(\d{3})(\d{3})(\d{1})/, "$1.$2.$3-$4");
    } else if (value.length > 5) {
        value = value.replace(/(\d{2})(\d{3})(\d{3})/, "$1.$2.$3");
    } else if (value.length > 2) {
        value = value.replace(/(\d{2})(\d{3})/, "$1.$2");
    }
    e.target.value = value;
});

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

    // Skip Step 4 (Documents) for Maricá and Minas Gerais
    if (step === 4 && (city === 'marica' || city === 'minas_gerais')) {
        showStep(5);
        return;
    }

    showStep(step);
}

function prevStep(step) {
    const city = document.getElementById('cidade').value;
    
    // Se estiver voltando durante uma edição, cancela o modo edição
    isEditingMode = false;

    // Skip Step 4 (Documents) when going back from 5 for Maricá and Minas Gerais
    if (step === 4 && (city === 'marica' || city === 'minas_gerais')) {
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
    const isSpecialCity = (city === 'marica' || city === 'minas_gerais');
    
    // Toggle required status for Step 4 fields based on city
    const step4Inputs = document.getElementById('step4').querySelectorAll('input[type="file"]');
    step4Inputs.forEach(input => {
        if (isSpecialCity) {
            input.required = false;
            input.classList.remove('required-field');
        } else {
            // Re-enable required if not special city, except for comprovante if termo is checked
            if (input.name === 'comprovante_residencia') {
                const levarTermo = document.getElementById('levar_termo');
                input.required = !(levarTermo && levarTermo.checked);
            } else {
                input.required = true;
            }
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
        bairro: 'Bairro', endereco: 'Endereço', google_maps_link: 'Localização Google Maps',
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
    const isSpecialCity = (city === 'marica' || city === 'minas_gerais');

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
                value = `<a href="${value}" target="_blank" class="text-primary text-decoration-none fw-bold">📍 Abrir no Google Maps</a>`;
            }

            // Formatação amigável
            if (field === 'tipoPessoa') value = value === 'pf' ? 'Pessoa Física' : 'Pessoa Jurídica';
            if (field === 'levar_termo') value = value ? 'Sim' : 'Não (Vou anexar comprovante)';
            
            if (field === 'cidade') {
                const cityMap = { 
                    marica: 'Maricá - RJ', muqui: 'Muqui - ES', piuma: 'Piúma - ES', 
                    mimoso: 'Mimoso do Sul - ES', cabo_frio: 'Cabo Frio - RJ', 
                    unamar: 'Unamar - RJ', sao_paulo: 'São Paulo - SP', outra: 'Outra' 
                };
                value = cityMap[value] || value;
            }
            if (field === 'plano') {
                let cityPlans = planDetails.default;
                if (city === 'muqui' || city === 'piuma') cityPlans = planDetails.muqui_piuma;
                else if (city === 'mimoso') cityPlans = planDetails.mimoso;
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

    // Financeiro
    const isFidelidade = formData.get('fidelidade') === 'sim';
    let price = '';
    
    if (city === 'marica') {
        price = isFidelidade ? 'R$ 100,00' : 'R$ 460,00';
    } else {
        price = isFidelidade ? 'GRÁTIS' : 'R$ 360,00';
    }

    html += `
        <div class="summary-section-header">RESUMO FINANCEIRO</div>
        <div class="summary-item">
            <span class="summary-label">Valor da Instalação:</span>
            <span class="summary-value fw-bold text-success">${price}</span>
        </div>
    `;

    summary.innerHTML = html;
}



function validateStep(step) {
    const city = document.getElementById('cidade').value;
    const type = document.getElementById('tipoPessoa').value;
    const levarTermo = document.getElementById('levar_termo') ? document.getElementById('levar_termo').checked : false;
    
    // Define os campos obrigatórios por passo
    const requiredFields = {
        1: ['documento', 'nome_razao', 'email', 'telefone'],
        2: ['cep', 'cidade', 'bairro', 'endereco', 'referencia'],
        3: ['plano', 'vencimento'],
        4: [], // Documentos variam
        5: ['data_instalacao', 'periodo_instalacao', 'origem']
    };

    // Ajustes específicos do Passo 1 (PF/PJ)
    if (step === 1) {
        if (type === 'pf') {
            requiredFields[1].push('rg', 'data_nascimento');
        } else {
            requiredFields[1].push('nome_fantasia');
        }
    }

    // Ajustes específicos do Passo 4 (Documentos)
    if (step === 4) {
        const isSpecialCity = (city === 'marica' || city === 'minas_gerais');
        if (!isSpecialCity) {
            if (!levarTermo) requiredFields[4].push('comprovante_residencia');
            requiredFields[4].push('foto_documento_frente', 'foto_documento_verso', 'selfie_documento');
        }
    }

    // Ajuste específico do Passo 5 (Pagamento)
    if (step === 5) {
        const fidInput = document.querySelector('input[name="fidelidade"]:checked');
        const isFidelidade = fidInput ? fidInput.value === 'sim' : true;
        if (city === 'marica' || !isFidelidade) {
            requiredFields[5].push('pagamento_instalacao');
        }
    }

    let valid = true;
    const fieldsToValidate = requiredFields[step] || [];
    
    fieldsToValidate.forEach(fieldName => {
        const input = document.getElementsByName(fieldName)[0] || document.getElementById(fieldName);
        if (!input) return;

        let isFieldValid = true;
        if (input.type === 'file') {
            isFieldValid = input.files && input.files.length > 0;
        } else {
            isFieldValid = input.value && input.value.trim() !== '';
        }

        // Validação extra para data de instalação
        if (fieldName === 'data_instalacao' && isFieldValid) {
            const selectedDate = new Date(input.value + 'T00:00:00');
            const tomorrow = new Date();
            tomorrow.setHours(0,0,0,0);
            tomorrow.setDate(tomorrow.getDate() + 1);
            if (selectedDate < tomorrow) {
                isFieldValid = false;
                showNotify('A data de instalação deve ser a partir de amanhã.', 'warning');
            }
        }

        if (!isFieldValid) {
            if (input.type === 'file') {
                const wrapper = input.closest('.file-upload-wrapper');
                if (wrapper) wrapper.style.borderColor = 'red';
            } else {
                input.style.borderColor = 'red';
            }
            valid = false;
        } else {
            if (input.type === 'file') {
                const wrapper = input.closest('.file-upload-wrapper');
                if (wrapper) wrapper.style.borderColor = '#ddd';
            } else {
                input.style.borderColor = '#ddd';
            }
        }
    });

    if (!valid && !document.querySelector('.toast.show')) {
        showNotify('Por favor, preencha todos os campos obrigatórios (*).', 'warning');
    }
    return valid;
}

// Logic for Cities
function handleCityChange() {
    const city = document.getElementById('cidade').value;
    const installationInfo = document.getElementById('installationInfo');
    const termoOption = document.getElementById('termo_option');
    const pagamentoWrapper = document.getElementById('pagamento_instalacao_wrapper');
    const pagamentoSelect = document.getElementById('pagamento_instalacao');

    // Update Plans list based on city
    updatePlanOptions(city);

    // Show/Hide installation info
    installationInfo.style.display = 'block';
    calculateInstallation();

    // Lógica para o campo de pagamento da instalação
    const fidInput = document.querySelector('input[name="fidelidade"]:checked');
    const isFidelidade = fidInput ? fidInput.value === 'sim' : true;

    if (city === 'marica') {
        pagamentoWrapper.style.display = 'block';
        if (isFidelidade) {
            pagamentoSelect.value = 'pix'; // Default para Maricá com fidelidade
        }
    } else if (city) {
        if (isFidelidade) {
            pagamentoWrapper.style.display = 'none';
            pagamentoSelect.value = 'gratis';
        } else {
            pagamentoWrapper.style.display = 'block';
        }
    }

    // Show/Hide Termo option (Unamar, Cabo Frio, SP)
    const canLevarTermo = ['cabo_frio', 'unamar', 'sao_paulo'].includes(city);
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

    let cityPlans = planDetails.default;
    if (city === 'muqui' || city === 'piuma') cityPlans = planDetails.muqui_piuma;
    else if (city === 'mimoso') cityPlans = planDetails.mimoso;

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

    if (city === 'marica') {
        const price = isFidelidade ? 100 : 460;
        installPriceSpan.innerText = `R$ ${price.toFixed(2).replace('.', ',')}`;
        pagamentoWrapper.style.display = 'block';
    } else if (city) {
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

    // Maricá e Minas Gerais (Antiga lógica)
    if (city === 'marica' || city === 'minas_gerais') {
        if (today >= 2 && today <= 10) {
            options = [{ day: '03', id: '107' }, { day: '06', id: '91' }, { day: '09', id: '106' }];
        } else if (today >= 11 && today <= 20) {
            options = [{ day: '13', id: '105' }, { day: '18', id: '93' }];
        } else {
            options = [{ day: '22', id: '160' }, { day: '26', id: '161' }, { day: '01', id: '159' }];
        }
    } else {
        // Novas Regiões (1, 3, 6, 7, 9, 13, 18)
        const days = ['01', '03', '06', '07', '09', '13', '18'];
        options = days.map(d => ({ day: d, id: 'IXC' }));
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
document.getElementById('registrationForm').onsubmit = function(e) {
    e.preventDefault();
    
    // Valida o último passo antes de submeter
    if (!validateStep(currentStep)) return;

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

// Masking inputs (simple version)
document.getElementById('cep').addEventListener('input', function(e) {
    let value = e.target.value.replace(/\D/g, '');
    if (value.length > 8) value = value.slice(0, 8);
    if (value.length > 5) {
        value = value.replace(/(\d{5})(\d{3})/, "$1-$2");
    }
    e.target.value = value;
});

document.getElementById('telefone').addEventListener('input', function(e) {
    let value = e.target.value.replace(/\D/g, '');
    if (value.length > 11) value = value.slice(0, 11);
    
    if (value.length > 10) {
        value = value.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3");
    } else if (value.length > 6) {
        value = value.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3");
    } else if (value.length > 2) {
        value = value.replace(/(\d{2})/, "($1) ");
    }
    e.target.value = value;
});
