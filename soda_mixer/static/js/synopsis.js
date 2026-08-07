// synopsis.js

let synopsisBottleScale = 1.0;
let synopsisSweetnessStyle = 'CRAFT';

let synopsisCoffeeStyle = 'HOT';
let synopsisCoffeeSize = 12;
let synopsisCoffeeBase = 'ESPRESSO';

let synopsisCryoScale = 32;

let llmStreamTriggered = false;

function formatImperialVolume(ml) {
    const oz = ml / 29.5735;
    if (oz >= 1.0) return oz.toFixed(1) + "oz";
    const tbsp = ml / 14.7868;
    if (tbsp >= 1.0) return tbsp.toFixed(1) + "tbsp";
    const tsp = ml / 4.92892;
    const roundedTsp = Math.round(tsp);
    return (roundedTsp < 1 ? 1 : roundedTsp) + "tsp";
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('Laboratory Synopsis Initialized.');
    const prefillData = window.SYNOPSIS_PREFILL;
    
    // If we have POST data, we use it. Otherwise, look for localStorage.
    let synthesisData = prefillData;
    if (!synthesisData) {
        const stored = localStorage.getItem('synopsis_data');
        if (stored) {
            try {
                synthesisData = JSON.parse(stored);
            } catch(e) {}
        }
    }

    if (synthesisData) {
        // Inject Lab Theme
        if (synthesisData.drink_type) {
            const dt = synthesisData.drink_type.toUpperCase();
            document.documentElement.classList.remove('theme-coffee', 'theme-cryo', 'theme-slushie', 'theme-soda');
            if (dt === 'COFFEE') {
                document.documentElement.classList.add('theme-coffee');
            } else if (dt === 'CRYO' || dt === 'SLUSHIE') {
                document.documentElement.classList.add('theme-cryo');
            } else {
                document.documentElement.classList.add('theme-soda');
            }
        }

        // Initialize scales if available in data, else use defaults
        if (synthesisData.bottleScale) synopsisBottleScale = synthesisData.bottleScale;
        if (synthesisData.sodaSweetnessStyle) synopsisSweetnessStyle = synthesisData.sodaSweetnessStyle;

        // Show scale toggles if it's SODA
        if (synthesisData.drink_type === 'soda' || synthesisData.drink_type === 'SODA') {
            document.getElementById('synopsisScaleContainer').style.display = 'block';
        } else if (synthesisData.drink_type === 'coffee' || synthesisData.drink_type === 'COFFEE') {
            document.getElementById('synopsisCoffeeContainer').style.display = 'block';
        } else if (synthesisData.drink_type === 'cryo' || synthesisData.drink_type === 'CRYO') {
            document.getElementById('synopsisCryoContainer').style.display = 'block';
        }

        populateSynopsis(synthesisData);
        triggerFlavorSynthesis(synthesisData);
        
        if (synthesisData.name) {
            document.getElementById('recipeNameField').value = synthesisData.name;
        }
    } else {
        document.getElementById('synthesisReportBody').innerHTML = "<div class='text-warning'>No compound data found in local storage or session. Please return to the laboratory.</div>";
    }
});

function setSynopsisScale(scale) {
    synopsisBottleScale = scale;
    // Update button classes
    const sodaBtns = { 1.0: 'scale1L', 0.5: 'scale05L', 0.355: 'scale12oz' };
    Object.entries(sodaBtns).forEach(([val, id]) => {
        const el = document.getElementById(id);
        if (el) {
            if (Math.abs(synopsisBottleScale - parseFloat(val)) < 0.01) {
                el.classList.add('active-lab-mode');
            } else {
                el.classList.remove('active-lab-mode');
            }
        }
    });
    
    if (window.SYNOPSIS_PREFILL) {
        triggerFlavorSynthesis(window.SYNOPSIS_PREFILL);
    }
}

function setSynopsisSweetness(style) {
    synopsisSweetnessStyle = style;
    // Update button classes
    document.getElementById('sweetnessCrisp').classList.toggle('active-lab-mode', style === 'CRISP');
    document.getElementById('sweetnessCraft').classList.toggle('active-lab-mode', style === 'CRAFT');
    document.getElementById('sweetnessFountain').classList.toggle('active-lab-mode', style === 'FOUNTAIN');
    
    if (window.SYNOPSIS_PREFILL) {
        triggerFlavorSynthesis(window.SYNOPSIS_PREFILL);
    }
}

function setSynopsisCoffeeStyle(style) {
    synopsisCoffeeStyle = style;
    document.getElementById('coffeeStyleHot').classList.toggle('active-lab-mode', style === 'HOT');
    document.getElementById('coffeeStyleIced').classList.toggle('active-lab-mode', style === 'ICED');
    document.getElementById('coffeeStyleShot').classList.toggle('active-lab-mode', style === 'SHOT');
    
    const sizeBtns = document.getElementById('coffeeSizeBtns');
    const baseBtnsContainer = document.getElementById('coffeeBaseBtns')?.parentElement;
    
    if (style === 'SHOT') {
        if (sizeBtns) {
            sizeBtns.innerHTML = `
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="coffeeSize1" onclick="setSynopsisCoffeeSize(1)">1 Shot</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="coffeeSize2" onclick="setSynopsisCoffeeSize(2)">2 Shots</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="coffeeSize3" onclick="setSynopsisCoffeeSize(3)">3 Shots</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="coffeeSize4" onclick="setSynopsisCoffeeSize(4)">4 Shots</button>
            `;
        }
        if (baseBtnsContainer) baseBtnsContainer.style.display = 'none';
        
        // Force base to espresso
        setSynopsisCoffeeBase('ESPRESSO');
        
        // Default to double shot if currently an invalid size
        if (![1, 2, 3, 4].includes(synopsisCoffeeSize)) {
            setSynopsisCoffeeSize(2);
        } else {
            setSynopsisCoffeeSize(synopsisCoffeeSize);
        }
    } else {
        if (sizeBtns) {
            sizeBtns.innerHTML = `
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="coffeeSize8" onclick="setSynopsisCoffeeSize(8)">8oz</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="coffeeSize12" onclick="setSynopsisCoffeeSize(12)">12oz</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="coffeeSize16" onclick="setSynopsisCoffeeSize(16)">16oz</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="coffeeSize20" onclick="setSynopsisCoffeeSize(20)">20oz</button>
            `;
        }
        if (baseBtnsContainer) baseBtnsContainer.style.display = '';
        
        // Default to 12oz if currently a shot size
        if ([1, 2, 3, 4].includes(synopsisCoffeeSize)) {
            setSynopsisCoffeeSize(12);
        } else {
            setSynopsisCoffeeSize(synopsisCoffeeSize);
        }
    }
    
    if (window.SYNOPSIS_PREFILL) triggerFlavorSynthesis(window.SYNOPSIS_PREFILL);
}

function setSynopsisCoffeeSize(size) {
    synopsisCoffeeSize = size;
    
    // Large cup sizes
    document.getElementById('coffeeSize8')?.classList.toggle('active-lab-mode', size === 8);
    document.getElementById('coffeeSize12')?.classList.toggle('active-lab-mode', size === 12);
    document.getElementById('coffeeSize16')?.classList.toggle('active-lab-mode', size === 16);
    document.getElementById('coffeeSize20')?.classList.toggle('active-lab-mode', size === 20);
    
    // Shot sizes
    document.getElementById('coffeeSize1')?.classList.toggle('active-lab-mode', size === 1);
    document.getElementById('coffeeSize2')?.classList.toggle('active-lab-mode', size === 2);
    document.getElementById('coffeeSize3')?.classList.toggle('active-lab-mode', size === 3);
    document.getElementById('coffeeSize4')?.classList.toggle('active-lab-mode', size === 4);
    
    if (window.SYNOPSIS_PREFILL) triggerFlavorSynthesis(window.SYNOPSIS_PREFILL);
}

function setSynopsisCoffeeBase(base) {
    synopsisCoffeeBase = base;
    document.getElementById('coffeeBaseEspresso').classList.toggle('active-lab-mode', base === 'ESPRESSO');
    document.getElementById('coffeeBaseBrew').classList.toggle('active-lab-mode', base === 'BREW');
    if (window.SYNOPSIS_PREFILL) triggerFlavorSynthesis(window.SYNOPSIS_PREFILL);
}

function setSynopsisCryoScale(scale) {
    synopsisCryoScale = scale;
    document.getElementById('cryoScale16').classList.toggle('active-lab-mode', scale === 16);
    document.getElementById('cryoScale32').classList.toggle('active-lab-mode', scale === 32);
    document.getElementById('cryoScale48').classList.toggle('active-lab-mode', scale === 48);
    document.getElementById('cryoScale64').classList.toggle('active-lab-mode', scale === 64);
    if (window.SYNOPSIS_PREFILL) triggerFlavorSynthesis(window.SYNOPSIS_PREFILL);
}

function populateSynopsis(data, chemistryData = null) {
    const list = document.getElementById('selectedIngredientsList');
    list.innerHTML = '';
    
    if (data.drink_type) {
        document.getElementById('drinkTypeField').value = data.drink_type;
    }
    
    // Default form inputs
    const formInputsContainer = document.createElement('div');
    formInputsContainer.style.display = 'none';

    if (data.ingredients && Array.isArray(data.ingredients)) {
        // If we have chemistry data, we render the big cards
        let hasChemistry = !!chemistryData && !!chemistryData.ingredients;
        let isSoda = data.drink_type === 'SODA' || data.drink_type === 'soda';
        let isCoffee = data.drink_type === 'COFFEE' || data.drink_type === 'coffee';
        let isCryo = data.drink_type === 'CRYO' || data.drink_type === 'cryo';
        
        let basesToRender = [];
        if (hasChemistry) {
            if (isSoda && chemistryData.ingredients.carbonated_water) {
                basesToRender.push({
                    name: chemistryData.ingredients.carbonated_water.name,
                    volume: chemistryData.ingredients.carbonated_water.volume_ml,
                    role: 'VOLUME FILLER',
                    category: 'CARBONATION'
                });
            } else if (isCoffee) {
                if (chemistryData.ingredients.coffee_base) {
                    basesToRender.push({
                        name: chemistryData.ingredients.coffee_base.name,
                        volume: chemistryData.ingredients.coffee_base.volume_oz * 29.5735,
                        role: 'COFFEE BASE',
                        category: 'COFFEE',
                        shots: chemistryData.ingredients.coffee_base.shots
                    });
                }

                if (chemistryData.ingredients.base_modifiers && chemistryData.ingredients.base_modifiers.length > 0) {
                    chemistryData.ingredients.base_modifiers.forEach(bm => {
                        basesToRender.push({
                            name: bm.name,
                            volume: bm.volume_oz * 29.5735,
                            role: 'BASE MODIFIER',
                            category: 'NEUTRAL'
                        });
                    });
                }

                if (chemistryData.ingredients.payload_filler && chemistryData.ingredients.payload_filler.name !== 'None') {
                    basesToRender.push({
                        name: chemistryData.ingredients.payload_filler.name,
                        volume: chemistryData.ingredients.payload_filler.volume_oz * 29.5735,
                        role: 'DAIRY / FILLER',
                        category: 'DAIRY',
                        isCorrected: chemistryData.ingredients.payload_filler.is_corrected,
                        payloadFiller: chemistryData.ingredients.payload_filler
                    });
                }
            } else if (isCryo && chemistryData.ingredients.filler) {
                basesToRender.push({
                    name: chemistryData.ingredients.filler.name,
                    volume: chemistryData.ingredients.filler.volume_ml,
                    role: 'BASE FILLER',
                    category: 'NEUTRAL'
                });
            }
        }

        // Change list layout to grid
        list.className = 'row w-100 g-2 mb-3 row-cols-1 row-cols-sm-2 row-cols-md-3 row-cols-lg-5 justify-content-center m-0';

        // Add Base Cards
        basesToRender.forEach(base => {
            let volumeDisplay = '';
            
            // Coffee Base Shots vs Volume
            if (base.role === 'COFFEE BASE' && base.shots > 0) {
                if (synopsisCoffeeBase === 'ESPRESSO') {
                     volumeDisplay = `${base.shots} shot${base.shots !== 1 ? 's' : ''}<br/><span class="small opacity-75 text-dim mt-1 d-block">${Math.round(base.volume)}ml / ${formatImperialVolume(base.volume)}</span>`;
                } else {
                     volumeDisplay = `${Math.round(base.volume)}ml / ${formatImperialVolume(base.volume)}`;
                }
            } else {
                 volumeDisplay = `${Math.round(base.volume)}ml / ${formatImperialVolume(base.volume)}`;
            }

            const el = document.createElement('div');
            el.className = 'col animate-fade-in d-flex align-items-stretch';
            
            let cardInnerHtml = '';
            
            if (base.isCorrected && base.payloadFiller) {
                const pri_ml = Math.round(base.payloadFiller.primary_volume_oz * 29.5735);
                const tex_ml = Math.round(base.payloadFiller.texturizer_volume_oz * 29.5735);
                cardInnerHtml = `
                    <div class="glass-card p-0 text-center w-100 h-100 d-flex flex-column border-white border-opacity-25" style="position: relative;">
                        <div class="p-2 border-bottom border-white border-opacity-10">
                            <span class="readout-label d-block mb-0" style="font-size: 0.75rem;">${base.role}</span>
                        </div>
                        <div class="d-flex flex-row flex-grow-1">
                            <div class="w-50 p-2 border-end border-white border-opacity-10 d-flex flex-column align-items-center justify-content-center">
                                <div class="fw-bold mb-1" style="font-size: 1.0rem;">${base.payloadFiller.primary_name}</div>
                                <div class="text-dim mb-2" style="font-size: 0.70rem;">Primary Filler</div>
                                <div class="text-lab-accent fw-black mt-auto" style="font-size: 0.85rem;">${pri_ml}ml<br/>${base.payloadFiller.primary_volume_oz.toFixed(1)}oz</div>
                            </div>
                            <div class="w-50 p-2 d-flex flex-column align-items-center justify-content-center">
                                <div class="fw-bold mb-1" style="font-size: 1.0rem;">${base.payloadFiller.texturizer_name}</div>
                                <div class="text-dim mb-2" style="font-size: 0.70rem;">Texture Anchor</div>
                                <div class="text-lab-accent fw-black mt-auto" style="font-size: 0.85rem;">${tex_ml}ml<br/>${base.payloadFiller.texturizer_volume_oz.toFixed(1)}oz</div>
                            </div>
                        </div>
                        <div class="p-2 border-top border-white border-opacity-10 text-dim" style="font-size: 0.7rem;">
                            ${Math.round(base.volume)}ml / ${formatImperialVolume(base.volume)}
                        </div>
                    </div>
                `;
            } else {
                cardInnerHtml = `
                    <div class="glass-card p-3 ingredient-card border-white border-opacity-25 w-100 h-100 d-flex flex-column justify-content-center align-items-center text-center">
                        <div class='small text-lab-accent fw-bold mb-2' style='letter-spacing: 1px; font-size: 0.65rem;'>${base.role}</div>
                        <h5 class='fw-black mb-1'>${base.name}</h5>
                        ${base.category ? `<div class="mb-2"><span class="badge-fizz bg-${base.category.toLowerCase().trim()}">${base.category}</span></div>` : ''}
                        <div class='text-lab-accent fw-bold mt-auto pt-2'>${volumeDisplay}</div>
                    </div>
                `;
            }
            el.innerHTML = cardInnerHtml;
            list.appendChild(el);
        });

        data.ingredients.forEach(ing => {
            let volumeMl = ing.amount || 0;
            let percentage = null;
            let isPrimary = false;
            let role = 'MODIFIER';
            let formattedImperial = formatImperialVolume(volumeMl);

            if (hasChemistry) {
                let matched = null;
                if (isSoda && chemistryData.ingredients.modifiers) {
                    matched = chemistryData.ingredients.modifiers.find(m => (m.id && m.id == ing.id) || m.name === ing.name);
                    if (matched) {
                        volumeMl = matched.volume_ml;
                        percentage = matched.percentage_of_syrup;
                    }
                } else if (isCoffee && chemistryData.ingredients.modifiers) {
                    matched = chemistryData.ingredients.modifiers.find(m => (m.id && m.id == ing.id) || m.name === ing.name);
                    if (matched) {
                        volumeMl = matched.volume_oz * 29.5735;
                        percentage = matched.percentage_of_liquid;
                    }
                } else if (isCryo && chemistryData.ingredients.modifiers) {
                    matched = chemistryData.ingredients.modifiers.find(m => (m.id && m.id == ing.id) || m.name === ing.name);
                    if (matched) {
                        volumeMl = matched.volume_ml;
                    }
                }

                if (matched) {
                    isPrimary = matched.is_primary || false;
                    role = isPrimary ? 'PRIMARY BASE' : 'MODIFIER';
                    formattedImperial = formatImperialVolume(volumeMl);
                }
            }

            // Don't render bases/dairy here if they were already rendered above
            let isBaseIng = false;
            if (isCoffee) {
                if (ing.type === 'COFFEE_BEAN' || ing.type === 'DAIRY' || ing.mixology_function === 'VOLUME_BASE') {
                    isBaseIng = true;
                }
            } else if (isCryo) {
                if (hasChemistry && chemistryData.ingredients.filler && 
                   ((chemistryData.ingredients.filler.id && chemistryData.ingredients.filler.id == ing.id) || 
                    chemistryData.ingredients.filler.name === ing.name)) {
                    isBaseIng = true;
                }
            } else if (isSoda) {
                if (hasChemistry && chemistryData.ingredients.payload_filler && 
                   ((chemistryData.ingredients.payload_filler.id && chemistryData.ingredients.payload_filler.id == ing.id) || 
                    chemistryData.ingredients.payload_filler.name === ing.name)) {
                    isBaseIng = true;
                }
            }
            
            if (!isBaseIng || !hasChemistry) {
                const el = document.createElement('div');
                el.className = 'col animate-fade-in d-flex align-items-stretch';
                el.innerHTML = `
                    <div class="glass-card p-3 ingredient-card border-white w-100 h-100 d-flex flex-column justify-content-center align-items-center text-center ${isPrimary ? 'border-primary glow-primary border-opacity-50' : 'border-opacity-25'}">
                        <div class='small text-lab-accent fw-bold mb-2' style='letter-spacing: 1px; font-size: 0.65rem;'>${role}</div>
                        ${isPrimary ? '<div class="badge bg-primary bg-opacity-25 text-primary border border-primary border-opacity-25 mx-auto mb-2" style="font-size: 0.6rem;"><i class="bi bi-star-fill me-1"></i>PRIMARY ANCHOR</div>' : ''}
                        <h5 class='fw-black mb-1'>${ing.name}</h5>
                        ${ing.category ? `<div class="mb-2"><span class="badge-fizz bg-${ing.category.toLowerCase().trim()}">${ing.category}</span></div>` : ''}
                        <div class='text-lab-accent fw-bold mt-auto pt-2'>${Math.round(volumeMl)}ml / ${formattedImperial} ${percentage !== null && percentage !== undefined ? `<br/><span class="small opacity-75 text-dim mt-1 d-block">(${percentage}%)</span>` : ''}</div>
                    </div>
                `;
                list.appendChild(el);
            }
            
            // Add hidden inputs for the form
            const idInput = document.createElement('input');
            idInput.type = 'hidden';
            idInput.name = 'ingredient_id';
            idInput.value = ing.id;
            formInputsContainer.appendChild(idInput);
            
            const amtInput = document.createElement('input');
            amtInput.type = 'hidden';
            amtInput.name = `amount_${ing.id}`;
            amtInput.value = volumeMl || 0;
            formInputsContainer.appendChild(amtInput);
        });
        
        // Append form inputs container
        list.appendChild(formInputsContainer);
    }
}

function triggerFlavorSynthesis(data) {
    const reportBody = document.getElementById('synthesisReportBody');
    
    // Fallback if no ingredients
    if (!data.ingredients || data.ingredients.length === 0) {
        reportBody.innerHTML = '<div>Synthesis aborted: No ingredients.</div>';
        return;
    }

    // Show loading spinner safely
    const topSection = document.getElementById('chemistryReportTop');
    if (!topSection) {
        reportBody.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border text-lab-accent" role="status"></div>
                <div class="mt-2 text-dim small">Generating molecular analysis...</div>
            </div>
        `;
    } else {
        topSection.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border text-lab-accent" role="status"></div>
                <div class="mt-2 text-dim small">Recalculating volumes...</div>
            </div>
        `;
    }

    // Map ingredients to what backend expects
    const mappedIngredients = data.ingredients.map(ing => {
        return {
            id: ing.id,
            name: ing.name,
            type: ing.type,
            ingredient_type: ing.type || ing.ingredient_type || 'SODA_SYRUP',
            physical_state: ing.physical_state,
            mixology_function: ing.mixology_function,
            is_primary: ing.isPrimary || false,
            amount: ing.amount || 20 // Default amount just in case
        };
    });

    let fetchUrl = '/api/soda/chemistry/';
    let payload = {
        ingredients: mappedIngredients
    };

    if (data.drink_type === 'COFFEE' || data.drink_type === 'coffee') {
        fetchUrl = '/api/coffee/chemistry/';
        
        let drinkCategory = 'Hot Coffee';
        if (synopsisCoffeeStyle === 'ICED') drinkCategory = 'Iced Coffee';
        else if (synopsisCoffeeStyle === 'SHOT') drinkCategory = 'Pure Espresso / Short Milk';
        
        payload.drink_category = drinkCategory;
        payload.cup_size_oz = synopsisCoffeeSize;
        
        payload.ingredients = payload.ingredients.map(ing => {
            const ingCopy = { ...ing };
            if ((ingCopy.type || '').toUpperCase() === 'COFFEE_BEAN' || (ingCopy.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN') {
                ingCopy.coffee_base_type = synopsisCoffeeBase.toLowerCase();
            }
            return ingCopy;
        });

        payload.coffee_style = synopsisCoffeeStyle;
        payload.drink_size_oz = synopsisCoffeeSize;
        payload.coffee_base_type = synopsisCoffeeBase;
    } else if (data.drink_type === 'CRYO' || data.drink_type === 'cryo') {
        fetchUrl = '/api/cryo/chemistry/';
        payload.batch_scale = synopsisCryoScale;
    } else {
        // default to SODA
        fetchUrl = '/api/soda/chemistry/';
        payload.sweetness_style = synopsisSweetnessStyle;
        payload.bottle_scale = synopsisBottleScale;
    }

    fetch(fetchUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.CSRF_TOKEN
        },
        body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(chemistryData => {
        // First re-render the cards with the calculated volumes
        populateSynopsis(data, chemistryData);
        
        // Now render the big report skeleton
        renderChemistryReport(chemistryData, data);

        // TRIGGER THE LLM SSE STREAM for Profile and Notes ONLY ONCE!
        if (!llmStreamTriggered) {
            triggerLlmStream(data);
            llmStreamTriggered = true;
        }
    })
    .catch(err => {
        console.error('Error fetching chemistry:', err);
        reportBody.innerHTML = `<div class="text-danger small mt-2">Analysis failed to generate.</div>`;
    });
}

function triggerLlmStream(data) {
    const sseUrl = `/api/ai/synthesize/?drink_type=${encodeURIComponent(data.drink_type || 'SODA')}&ingredients=${encodeURIComponent(JSON.stringify(data.ingredients))}`;
    
    // We target the inner text spans
    const profileText = document.getElementById('llmProfileDescriptionText');
    const profileSpinner = document.getElementById('llmProfileDescriptionSpinner');
    const notesText = document.getElementById('llmMixologistNotesText');
    const notesSpinner = document.getElementById('llmMixologistNotesSpinner');
    
    if (window.activeSynopsisStream) {
        window.activeSynopsisStream.close();
    }
    
    window.activeSynopsisStream = new EventSource(sseUrl);
    
    window.activeSynopsisStream.addEventListener('message', function(e) {
        if (profileSpinner) profileSpinner.remove();
        if (profileText) profileText.innerHTML += e.data;
    });
    
    window.activeSynopsisStream.addEventListener('mixologist_notes', function(e) {
        if (notesSpinner) notesSpinner.remove();
        if (notesText) notesText.innerHTML += e.data;
    });
    
    window.activeSynopsisStream.addEventListener('remove_spinner', function(e) {
        if (profileSpinner) profileSpinner.remove();
        if (notesSpinner) notesSpinner.remove();
        window.activeSynopsisStream.close();
        window.activeSynopsisStream = null;
    });
    
    window.activeSynopsisStream.onerror = function(e) {
        if (profileSpinner) profileSpinner.remove();
        if (notesSpinner) notesSpinner.remove();
        window.activeSynopsisStream.close();
        window.activeSynopsisStream = null;
    };
}

function renderChemistryReport(data, originalData) {
    let topSection = document.getElementById('chemistryReportTop');
    if (!topSection) {
        const container = document.getElementById('synthesisReportBody');
        container.innerHTML = `
            <div id="chemistryReportTop"></div>
            <div id="chemistryReportBottom">
                <h6 class="readout-label text-lab-accent mb-3 mt-5">PREPARATION STEPS</h6>
                <div id="prepStepsContainer" class="text-white opacity-90 small mb-4 lh-lg"></div>
                
                <h6 class="readout-label text-lab-accent mb-3">AI MIXOLOGIST NOTES</h6>
                <div class="text-white opacity-90 small lh-lg mb-4">
                    <i class="bi bi-chat-quote text-lab-accent me-2"></i>
                    <span id="llmMixologistNotesText"></span>
                    <span id="llmMixologistNotesSpinner" class="spinner-border spinner-border-sm text-lab-accent ms-2"></span>
                </div>
                
                <h6 class="readout-label text-lab-accent mb-3 mt-4">OVERALL PROFILE DESCRIPTION</h6>
                <div class="text-white opacity-90 small lh-lg">
                    <span id="llmProfileDescriptionText"></span>
                    <span id="llmProfileDescriptionSpinner" class="spinner-border spinner-border-sm text-lab-accent ms-2"></span>
                </div>
            </div>
        `;
        topSection = document.getElementById('chemistryReportTop');
    }
    
    // Safety check for backend errors
    if (data.error) {
        topSection.innerHTML = `<div class="text-danger">Analysis Error: ${data.error}</div>`;
        return;
    }
    
    let isSoda = originalData.drink_type === 'SODA' || originalData.drink_type === 'soda';
    let isCoffee = originalData.drink_type === 'COFFEE' || originalData.drink_type === 'coffee';
    let isCryo = originalData.drink_type === 'CRYO' || originalData.drink_type === 'cryo';

    let validationHtml = '';
    const validationMsg = data.recipe_validation || 'Pass';
    if (validationMsg.toLowerCase() !== 'pass') {
        const isWarning = validationMsg.toLowerCase().includes('warning');
        const alertClass = isWarning ? 'alert-warning border-warning text-warning' : 'alert-danger border-danger text-danger';
        const iconClass = isWarning ? 'bi-exclamation-triangle-fill' : 'bi-x-circle-fill';
        validationHtml = `
            <div class="alert ${alertClass} bg-opacity-10 border border-opacity-20 d-flex align-items-center gap-2 mb-3 py-2 rounded-3">
                <i class="bi ${iconClass}"></i>
                <div class="fw-bold small">${validationMsg}</div>
            </div>
        `;
    }

    let html = `
        ${validationHtml}
        
        <div class="row g-4 mb-4">
            <div class="col-md-6">
                <h6 class="readout-label text-lab-accent mb-3">CHEMISTRY METRICS</h6>
    `;
    
    if (isCoffee) {
        html += `
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Body Intensity</span>
                    <span class="fw-bold">${data.aggregate_base_metrics.calculated_body.toFixed(2)}</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Acidity Score</span>
                    <span class="fw-bold">${data.aggregate_base_metrics.calculated_acidity.toFixed(2)}</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Bitterness Score</span>
                    <span class="fw-bold">${data.aggregate_base_metrics.calculated_bitterness.toFixed(2)}</span>
                </div>
        `;
    } else {
        html += `
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Sweetness Rating</span>
                    <span class="fw-bold">${data.extraction_analysis.sweetness.toFixed(1)}/5.0</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Acidity Score</span>
                    <span class="fw-bold">${data.extraction_analysis.acidity.toFixed(2)}/5.0</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Bitterness Score</span>
                    <span class="fw-bold">${data.extraction_analysis.bitterness.toFixed(2)}/5.0</span>
                </div>
        `;
    }
    
    html += `
            </div>
            
            <div class="col-md-6">
                <h6 class="readout-label text-lab-accent mb-3">VOLUMETRIC BUDGETS</h6>
    `;
    
    if (isSoda) {
        html += `
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Sweetness Style</span>
                    <span class="fw-bold">${synopsisSweetnessStyle}</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Batch Scale</span>
                    <span class="fw-bold">${synopsisBottleScale.toFixed(1)}L Bottle</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">${data.ingredients.carbonated_water ? data.ingredients.carbonated_water.name : 'Carbonated Water'}</span>
                    <span class="fw-bold">${data.ingredients.carbonated_water ? data.ingredients.carbonated_water.volume_ml : 0} ml</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Total Syrup Volume</span>
                    <span class="fw-bold">${data.drink_metrics.total_syrup_volume_ml} ml / ${data.drink_metrics.maximum_syrup_limit_ml} ml max</span>
                </div>
        `;
    } else if (isCoffee) {
        html += `
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Coffee Style</span>
                    <span class="fw-bold">${synopsisCoffeeStyle}</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Drink Size</span>
                    <span class="fw-bold">${synopsisCoffeeSize} oz</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Coffee Base</span>
                    <span class="fw-bold">${synopsisCoffeeBase}</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Base Volume</span>
                    <span class="fw-bold">${data.ingredients.coffee_base ? data.ingredients.coffee_base.volume_oz : 0} oz</span>
                </div>
        `;
    } else if (isCryo) {
        html += `
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Batch Scale</span>
                    <span class="fw-bold">${synopsisCryoScale} oz</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Target Volume</span>
                    <span class="fw-bold">${data.drink_metrics.target_volume_ml} ml</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Achieved Brix</span>
                    <span class="fw-bold">${data.drink_metrics.achieved_brix}%</span>
                </div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                    <span class="text-dim">Filler Volume</span>
                    <span class="fw-bold">${data.ingredients.filler ? data.ingredients.filler.volume_ml : 0} ml</span>
                </div>
        `;
    }

    html += `
            </div>
        </div>
        <h6 class="readout-label text-lab-accent mb-3 mt-4">CALCULATED EXTRACTS</h6>
    `;
    
    if (isSoda && data.ingredients.carbonated_water) {
        html += `
            <div class="small text-dim mb-1" style="font-size: 0.65rem; letter-spacing: 1px;">WATER BASE</div>
            <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-3">
                <span class="fw-bold">${data.ingredients.carbonated_water.name}</span>
                <span class="fw-bold text-white">${data.ingredients.carbonated_water.volume_ml} ml</span>
            </div>
            <div class="small text-dim mb-1" style="font-size: 0.65rem; letter-spacing: 1px;">FLAVOR SYRUPS</div>
        `;
        if (data.ingredients.modifiers) {
            data.ingredients.modifiers.forEach(mod => {
                let role = mod.is_primary ? 'Primary Base' : 'Modifier';
                html += `
                    <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                        <span class="fw-bold">${mod.name} <span class="text-dim fw-normal">(${role})</span></span>
                        <span class="fw-bold text-white">${mod.volume_ml} ml <span class="text-dim fw-normal">(${mod.percentage_of_syrup}%)</span></span>
                    </div>
                `;
            });
        }
    } else if (isCoffee) {
        if (data.ingredients.coffee_base) {
            html += `
                <div class="small text-dim mb-1" style="font-size: 0.65rem; letter-spacing: 1px;">COFFEE BASE</div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-3">
                    <span class="fw-bold">${data.ingredients.coffee_base.name}</span>
                    <span class="fw-bold text-white">${data.ingredients.coffee_base.volume_oz} oz ${data.ingredients.coffee_base.shots > 0 ? `(${data.ingredients.coffee_base.shots} shots)` : ''}</span>
                </div>
            `;
        }
        if (data.ingredients.dairy_or_filler && data.ingredients.dairy_or_filler.name !== 'None') {
            html += `
                <div class="small text-dim mb-1" style="font-size: 0.65rem; letter-spacing: 1px;">DAIRY / FILLER</div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-3">
                    <span class="fw-bold">${data.ingredients.dairy_or_filler.name}</span>
                    <span class="fw-bold text-white">${data.ingredients.dairy_or_filler.volume_oz} oz</span>
                </div>
            `;
        }
        if (data.ingredients.modifiers && data.ingredients.modifiers.length > 0) {
            html += `<div class="small text-dim mb-1" style="font-size: 0.65rem; letter-spacing: 1px;">FLAVOR SYRUPS</div>`;
            data.ingredients.modifiers.forEach(mod => {
                html += `
                    <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                        <span class="fw-bold">${mod.name}</span>
                        <span class="fw-bold text-white">${mod.volume_oz} oz</span>
                    </div>
                `;
            });
        }
    } else if (isCryo) {
        if (data.ingredients.filler) {
            html += `
                <div class="small text-dim mb-1" style="font-size: 0.65rem; letter-spacing: 1px;">BASE FILLER</div>
                <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-3">
                    <span class="fw-bold">${data.ingredients.filler.name}</span>
                    <span class="fw-bold text-white">${data.ingredients.filler.volume_ml} ml</span>
                </div>
            `;
        }
        if (data.ingredients.modifiers && data.ingredients.modifiers.length > 0) {
            html += `<div class="small text-dim mb-1" style="font-size: 0.65rem; letter-spacing: 1px;">FLAVOR SYRUPS</div>`;
            data.ingredients.modifiers.forEach(mod => {
                html += `
                    <div class="d-flex justify-content-between border-bottom border-white border-opacity-10 pb-2 mb-2">
                        <span class="fw-bold">${mod.name}</span>
                        <span class="fw-bold text-white">${mod.volume_ml} ml</span>
                    </div>
                `;
            });
        }
    }
    
    topSection.innerHTML = html;
    
    // Update prep steps safely
    const prepContainer = document.getElementById('prepStepsContainer');
    if (prepContainer) {
        prepContainer.innerHTML = (data.preparation_steps || []).map(step => `<div class="mb-2">${step}</div>`).join('');
    }
}

function fetchSuggestName() {
    const suggestBtn = document.getElementById('suggestBtn');
    const nameField = document.getElementById('recipeNameField');
    const drinkType = document.getElementById('drinkTypeField').value;
    
    const ids = Array.from(document.querySelectorAll('input[name="ingredient_id"]')).map(el => el.value);
    
    suggestBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
    
    fetch('/api/generate-name/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.CSRF_TOKEN
        },
        body: JSON.stringify({ ingredient_ids: ids, drink_type: drinkType })
    })
    .then(r => r.json())
    .then(data => {
        if (data.name) {
            nameField.value = data.name;
        }
    })
    .catch(e => console.error("Error suggesting name:", e))
    .finally(() => {
        suggestBtn.innerHTML = '<i class="bi bi-magic text-lab-accent"></i>';
    });
}

function interceptAndSave() {
    const form = document.getElementById('mixerForm');
    const nameField = document.getElementById('recipeNameField');
    if (!nameField.value.trim()) {
        alert("Please assign a nomenclature to this formulation before archiving.");
        nameField.focus();
        return;
    }
    
    const descField = document.getElementById('recipeDescriptionField');
    if (descField) {
        let fullDesc = "";
        const aiProfile = document.getElementById('llmProfileDescriptionText');
        const mixNotes = document.getElementById('llmMixologistNotesText');
        
        if (aiProfile && aiProfile.innerText.trim()) {
            fullDesc += aiProfile.innerText.trim() + "\n\n";
        }
        if (mixNotes && mixNotes.innerText.trim()) {
            fullDesc += "AI Mixologist Notes:\n" + mixNotes.innerText.trim();
        }
        
        descField.value = fullDesc.trim();
    }
    
    const saveBtn = document.getElementById('saveMixBtn');
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> ARCHIVING...';
    
    form.submit();
}
