// Document Auto-detection logic
function handleDocumentInput() {
    const input = document.getElementById('documento');
    let value = input.value.replace(/\D/g, '');
    
    // Apply masks based on length
    if (value.length <= 11) {
        // CPF Mask
        if (value.length > 9) {
            value = value.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
        } else if (value.length > 6) {
            value = value.replace(/(\d{3})(\d{3})(\d{3})/, "$1.$2.$3");
        } else if (value.length > 3) {
            value = value.replace(/(\d{3})(\d{3})/, "$1.$2");
        }
    } else {
        // CNPJ Mask
        if (value.length > 14) value = value.slice(0, 14);
        if (value.length > 12) {
            value = value.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
        } else if (value.length > 8) {
            value = value.replace(/(\d{2})(\d{3})(\d{3})(\d{4})/, "$1.$2.$3/$4");
        } else if (value.length > 5) {
            value = value.replace(/(\d{2})(\d{3})(\d{3})/, "$1.$2.$3");
        } else if (value.length > 2) {
            value = value.replace(/(\d{2})(\d{3})/, "$1.$2");
        }
    }
    input.value = value;

    // Detection logic
    const cleanValue = value.replace(/\D/g, '');
    const typeHidden = document.getElementById('tipoPessoa');
    const pfOnly = document.querySelectorAll('.pf-only');
    const pjOnly = document.querySelectorAll('.pj-only');
    const labelNome = document.getElementById('labelNome');
    const inputNome = document.getElementById('nome');
    const nomeFantasia = document.getElementById('nome_fantasia');
    const contratoSocial = document.getElementById('contrato_social');
    const rg = document.getElementById('rg');
    const dataNascimento = document.getElementById('data_nascimento');

    if (cleanValue.length > 11) {
        // Switch to PJ
        typeHidden.value = 'pj';
        pfOnly.forEach(el => el.style.display = 'none');
        pjOnly.forEach(el => {
            el.style.display = el.classList.contains('row') ? 'flex' : 'block';
        });
        labelNome.innerText = 'Razão Social *';
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
        labelNome.innerText = 'Nome Completo *';
        inputNome.placeholder = 'Digite seu nome completo';
        if (nomeFantasia) nomeFantasia.required = false;
        if (contratoSocial) contratoSocial.required = false;
        if (rg) rg.required = true;
        if (dataNascimento) dataNascimento.required = true;
    }
}

// File Upload Listener
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

        if (input) {
            input.addEventListener('change', function(e) {
                if (this.files && this.files.length > 0) {
                    const fileName = this.files[0].name;
                    if (info) info.innerText = `Arquivo selecionado: ${fileName}`;
                    if (wrapper) wrapper.classList.add('file-selected');
                } else {
                    if (info) info.innerText = 'Clique para selecionar o arquivo';
                    if (wrapper) wrapper.classList.remove('file-selected');
                }
            });
        }
    });
});

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

function nextStep(step) {
    const city = document.getElementById('cidade').value;
    
    if (!validateStep(currentStep)) return;

    // Skip Step 4 (Documents) for Maricá and Minas Gerais
    if (step === 4 && (city === 'marica' || city === 'minas_gerais')) {
        showStep(5);
        return;
    }

    showStep(step);
}

function prevStep(step) {
    const city = document.getElementById('cidade').value;

    // Skip Step 4 (Documents) when going back from 5 for Maricá and Minas Gerais
    if (step === 4 && (city === 'marica' || city === 'minas_gerais')) {
        showStep(3);
        return;
    }

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
                <button type="button" class="btn-edit" onclick="showStep(${config.step})">Editar</button>
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
    const inputs = document.getElementById(`step${step}`).querySelectorAll('input[required], select[required], textarea[required], input[min]');
    let valid = true;
    inputs.forEach(input => {
        if (!input.value || !input.checkValidity()) {
            input.style.borderColor = 'red';
            valid = false;
            
            // Show specific message for date if invalid
            if (input.id === 'data_instalacao' && input.validity.rangeUnderflow) {
                showNotify('A data de instalação deve ser a partir de amanhã.', 'warning');
            }
        } else {
            input.style.borderColor = '#ddd';
        }
    });

    if (!valid && !document.querySelector('.toast.show')) {
        showNotify('Por favor, preencha todos os campos corretamente.', 'warning');
    }
    return valid;
}

// Logic for Cities
function handleCityChange() {
    const city = document.getElementById('cidade').value;
    const installationInfo = document.getElementById('installationInfo');
    const termoOption = document.getElementById('termo_option');

    // Update Plans list based on city
    updatePlanOptions(city);

    // Show/Hide installation info
    installationInfo.style.display = 'block';
    calculateInstallation();

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
            input.required = false;
        } else {
            uploadWrapper.style.opacity = '1';
            uploadWrapper.style.pointerEvents = 'auto';
            input.required = true;
        }
    }
}

function calculateInstallation() {
    const city = document.getElementById('cidade').value;
    const fidInput = document.querySelector('input[name="fidelidade"]:checked');
    if (!fidInput) return;
    
    const isFidelidade = fidInput.value === 'sim';
    const installPriceSpan = document.getElementById('installPrice');

    if (city === 'marica') {
        const price = isFidelidade ? 100 : 460;
        installPriceSpan.innerText = `R$ ${price.toFixed(2).replace('.', ',')}`;
    } else if (city) {
        const price = isFidelidade ? 0 : 360;
        installPriceSpan.innerText = isFidelidade ? 'GRÁTIS' : `R$ ${price.toFixed(2).replace('.', ',')}`;
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
    
    const formData = new FormData(this);
    
    // Get the CSRF token from the cookie
    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    fetch('', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken,
        },
        body: formData
    })
    .then(response => {
        if (response.ok) {
            document.getElementById('registrationForm').style.display = 'none';
            
            // Remove error-prone header selector
            const header = document.querySelector('.form-header');
            if (header) header.style.display = 'none';
            
            document.getElementById('successMessage').style.display = 'block';
            window.scrollTo(0, 0);
        } else {
            showNotify('Erro ao enviar o cadastro. Por favor, tente novamente.', 'danger');
        }
    })
    .catch(error => {
        console.error('Erro:', error);
        showNotify('Erro ao enviar o cadastro. Por favor, tente novamente.', 'danger');
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
