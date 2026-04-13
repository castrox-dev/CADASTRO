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
    const nomeFantasia = document.getElementById('nomeFantasia');
    const contratoSocial = document.getElementById('contratoSocial');
    const rg = document.getElementById('rg');
    const dataNascimento = document.getElementById('dataNascimento');

    if (cleanValue.length > 11) {
        // Switch to PJ
        typeHidden.value = 'pj';
        pfOnly.forEach(el => el.style.display = 'none');
        pjOnly.forEach(el => {
            el.style.display = el.classList.contains('row') ? 'flex' : 'block';
        });
        labelNome.innerText = 'Razão Social *';
        inputNome.placeholder = 'Digite a Razão Social';
        nomeFantasia.required = true;
        contratoSocial.required = true;
        rg.required = false;
        dataNascimento.required = false;
    } else {
        // Default to PF
        typeHidden.value = 'pf';
        pfOnly.forEach(el => {
            el.style.display = el.classList.contains('row') ? 'flex' : 'block';
        });
        pjOnly.forEach(el => el.style.display = 'none');
        labelNome.innerText = 'Nome Completo *';
        inputNome.placeholder = 'Digite seu nome completo';
        nomeFantasia.required = false;
        contratoSocial.required = false;
        rg.required = true;
        dataNascimento.required = true;
    }
}

// File Upload Listener
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('contratoSocial');
    const fileWrapper = document.querySelector('.file-upload-wrapper');
    const fileInfo = document.querySelector('.file-upload-info');

    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            if (this.files && this.files.length > 0) {
                const fileName = this.files[0].name;
                fileInfo.innerText = `Arquivo selecionado: ${fileName}`;
                fileWrapper.classList.add('file-selected');
            } else {
                fileInfo.innerText = 'Clique para selecionar o arquivo';
                fileWrapper.classList.remove('file-selected');
            }
        });
    }
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
    document.getElementById('google_maps_link').value = directLink;
    
    showNotify('Localização marcada no mapa!', 'success');
}

// Plan Change logic
const planDetails = {
    essencial: {
        desc: "R$ 59,99/mês (até o vencimento)<br>R$ 79,99/mês (após vencimento)<br>Instalação em até 48h<br>Permanência 12 meses",
        opcional: "Deseja alugar roteador Wi-Fi por R$ 10,00/mês?"
    },
    rapido: {
        desc: "R$ 79,99/mês* (até o vencimento)<br>R$ 99,99/mês* (após vencimento)<br>Super Wi-Fi 5Ghz incluso<br>Permanência 12 meses",
        opcional: null
    },
    turbo: {
        desc: "R$ 99,99/mês* (até o vencimento)<br>R$ 119,99/mês* (após vencimento)<br>Ideal para gamers e streamers<br>Super Wi-Fi 5Ghz incluso<br>Permanência 12 meses",
        opcional: null
    },
    ultra: {
        desc: "R$ 119,99/mês* (até o vencimento)<br>R$ 139,99/mês* (após vencimento)<br>Watch TV, Paramount, Qualifica, Mediquo e McAfee inclusos<br>Permanência 12 meses",
        opcional: null
    },
    "1giga": {
        desc: "R$ 149,99 (até o vencimento)<br>R$ 169,99 (valor normal)<br>Wi-Fi 6 incluso 🚀<br>Contrato 12 meses",
        opcional: "Deseja Repetidor Mesh por apenas R$ 29,99 mensais?"
    }
};

function handlePlanChange() {
    const plan = document.getElementById('plano').value;
    const detailsBox = document.getElementById('planDetails');
    const descDiv = document.getElementById('planDescription');
    const opcionalGroup = document.getElementById('opcionaisGroup');
    const opcionalLabel = document.getElementById('opcionalLabel');

    if (plan && planDetails[plan]) {
        detailsBox.style.display = 'block';
        descDiv.innerHTML = `<strong>Detalhes do Plano:</strong><br>${planDetails[plan].desc}`;
        
        if (planDetails[plan].opcional) {
            opcionalGroup.style.display = 'block';
            opcionalLabel.innerText = planDetails[plan].opcional;
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

function showStep(step) {
    document.querySelectorAll('.form-step').forEach(s => s.classList.remove('active'));
    document.getElementById(`step${step}`).classList.add('active');
    
    // Update progress bar
    const progress = document.getElementById('progress');
    progress.style.width = `${(step / 5) * 100}%`;
    
    if (step === 5) {
        populateSummary();
    }
    
    currentStep = step;
    window.scrollTo(0, 0);
}

function nextStep(step) {
    if (validateStep(currentStep)) {
        showStep(step);
    }
}

function populateSummary() {
    const summary = document.getElementById('confirmationSummary');
    const form = document.getElementById('registrationForm');
    const formData = new FormData(form);
    
    let html = '';
    
    const sections = {
        'Dados Cadastrais': { fields: ['documento', 'tipoPessoa', 'nome', 'nomeFantasia', 'rg', 'inscricaoEstadual', 'contratoSocial', 'dataNascimento', 'email', 'telefone'], step: 1 },
        'Endereço': { fields: ['cep', 'cidade', 'bairro', 'endereco', 'google_maps_link', 'referencia'], step: 2 },
        'Plano e Vencimento': { fields: ['plano', 'fidelidade', 'vencimento', 'opcional'], step: 3 },
        'Instalação': { fields: ['pagamento', 'dataInstalacao', 'periodoInstalacao', 'origem'], step: 4 }
    };

    const labels = {
        documento: 'CPF/CNPJ', tipoPessoa: 'Tipo de Pessoa', nome: 'Nome/Razão Social', 
        nomeFantasia: 'Nome Fantasia', rg: 'RG', 
        inscricaoEstadual: 'Inscrição Estadual', contratoSocial: 'Contrato Social',
        dataNascimento: 'Data de Nascimento',
        email: 'E-mail', telefone: 'Telefone', cep: 'CEP', cidade: 'Cidade',
        bairro: 'Bairro', endereco: 'Endereço', google_maps_link: 'Localização Google Maps',
        referencia: 'Referência',
        plano: 'Plano', fidelidade: 'Fidelidade', vencimento: 'Dia de Vencimento',
        opcional: 'Opcional do Plano', pagamento: 'Modo de Pagamento',
        dataInstalacao: 'Data Instalação', periodoInstalacao: 'Período', origem: 'Origem'
    };

    for (const [section, config] of Object.entries(sections)) {
        html += `
            <div class="summary-section-header">
                <span>${section}</span>
                <button type="button" class="btn-edit" onclick="showStep(${config.step})">Editar</button>
            </div>
        `;
        config.fields.forEach(field => {
            let value = formData.get(field);
            
            // Tratamento especial para arquivos no resumo
            if (field === 'contratoSocial') {
                const fileInput = document.getElementById('contratoSocial');
                value = (fileInput.files && fileInput.files.length > 0) ? `📎 ${fileInput.files[0].name}` : null;
            }

            if (!value) return;

            // Tratamento especial para links de mapa
            if (field === 'google_maps_link') {
                value = `<a href="${value}" target="_blank" class="text-primary text-decoration-none">📍 Abrir no Google Maps</a>`;
            }

            // Formatação amigável
            if (field === 'tipoPessoa') {
                value = value === 'pf' ? 'Pessoa Física' : 'Pessoa Jurídica';
            }
            if (field === 'cidade') {
                const cityMap = { marica: 'Maricá', minas_gerais: 'Minas Gerais', outra: 'Outra' };
                value = cityMap[value] || value;
            }
            if (field === 'plano') {
                const planMap = { 
                    essencial: 'Plano Essencial – 240 MEGA', 
                    rapido: 'Plano Rápido - 400 Mega',
                    turbo: 'Plano Turbo - 500 Mega',
                    ultra: 'Plano Ultra - 600 Mega',
                    '1giga': 'Plano Novo – 1 GIGA'
                };
                value = planMap[value] || value;
            }
            if (field === 'fidelidade' || field === 'opcional') {
                value = value === 'sim' ? 'Sim' : 'Não';
            }
            if (field === 'periodoInstalacao') {
                value = value === 'manha' ? 'Manhã' : 'Tarde';
            }

            html += `
                <div class="summary-item">
                    <span class="summary-label">${labels[field]}:</span>
                    <span class="summary-value">${value}</span>
                </div>
            `;
        });
    }

    // Adiciona informação de instalação se for Maricá
    if (formData.get('cidade') === 'marica') {
        const isFidelidade = formData.get('fidelidade') === 'sim';
        const price = isFidelidade ? 'R$ 100,00' : 'R$ 460,00';
        html += `
            <div class="summary-section-header">Resumo Financeiro</div>
            <div class="summary-item">
                <span class="summary-label">Valor da Instalação:</span>
                <span class="summary-value">${price}</span>
            </div>
        `;
    }

    summary.innerHTML = html;
}

function prevStep(step) {
    showStep(step);
}

function validateStep(step) {
    const inputs = document.getElementById(`step${step}`).querySelectorAll('input[required], select[required], textarea[required]');
    let valid = true;
    inputs.forEach(input => {
        if (!input.value) {
            input.style.borderColor = 'red';
            valid = false;
        } else {
            input.style.borderColor = '#ddd';
        }
    });

    if (!valid) {
        showNotify('Por favor, preencha todos os campos obrigatórios.', 'warning');
    }
    return valid;
}

// Logic for Maricá and MG
function handleCityChange() {
    const city = document.getElementById('cidade').value;
    const fidelidadeGroup = document.getElementById('fidelidadeGroup');
    const installationInfo = document.getElementById('installationInfo');
    const vencimentoSelect = document.getElementById('vencimento');

    // Show/Hide installation info based on city
    if (city === 'marica') {
        installationInfo.style.display = 'block';
        calculateInstallation();
    } else {
        installationInfo.style.display = 'none';
    }

    // Update Vencimento options
    updateVencimentoOptions(city);
}

function calculateInstallation() {
    const city = document.getElementById('cidade').value;
    const isFidelidade = document.querySelector('input[name="fidelidade"]:checked').value === 'sim';
    const installPriceSpan = document.getElementById('installPrice');

    if (city === 'marica') {
        const price = isFidelidade ? 100 : 460;
        installPriceSpan.innerText = `R$ ${price.toFixed(2).replace('.', ',')}`;
    }
}

function updateVencimentoOptions(city) {
    const vencimentoSelect = document.getElementById('vencimento');
    const vencimentoIdInfo = document.getElementById('vencimentoIdInfo');
    vencimentoSelect.innerHTML = '<option value="">Selecione o vencimento</option>';
    vencimentoIdInfo.innerText = '';

    const today = new Date().getDate();
    let options = [];

    if (city === 'marica' || city === 'minas_gerais') {
        // Specific logic for Maricá and MG
        if (today >= 2 && today <= 10) {
            options = [
                { day: '03', id: '107' },
                { day: '06', id: '91' },
                { day: '09', id: '106' }
            ];
        } else if (today >= 11 && today <= 20) {
            options = [
                { day: '13', id: '105' },
                { day: '18', id: '93' }
            ];
        } else { // 21 to 1
            options = [
                { day: '22', id: '160' },
                { day: '26', id: '161' },
                { day: '01', id: '159' }
            ];
        }
    } else {
        // Default options for other cities
        options = [
            { day: '05', id: 'DEFAULT' },
            { day: '10', id: 'DEFAULT' },
            { day: '15', id: 'DEFAULT' },
            { day: '20', id: 'DEFAULT' }
        ];
    }

    options.forEach(opt => {
        const el = document.createElement('option');
        el.value = opt.day;
        el.dataset.id = opt.id;
        el.textContent = `Dia ${opt.day}`;
        vencimentoSelect.appendChild(el);
    });

    vencimentoSelect.onchange = function() {
        const selected = vencimentoSelect.options[vencimentoSelect.selectedIndex];
        if (selected.dataset.id && selected.dataset.id !== 'DEFAULT') {
            vencimentoIdInfo.innerText = `ID Interno: ${selected.dataset.id}`;
        } else {
            vencimentoIdInfo.innerText = '';
        }
    };
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
            document.querySelector('.form-header').style.display = 'none';
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
